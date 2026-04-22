"""Time Anomaly Agent v1 — 5-node LangGraph state machine.

Replaces the single-shot LLM classifier that lived in this file
pre-sprint. Reference: .cursor/plans/time_anomaly_v1_build.plan.md
and files/Time_Anomaly_Agent_v1_Build_Spec.md (Cortney).

Graph shape:

    detect ─┬── end            (no alert fires; quiet path)
            └── outreach ── wait_recheck ─┬── close (employee corrected)
                                          └── escalate_hitl ── end

Durable pause/resume between outreach and wait_recheck is provided by
LangGraph's Postgres checkpointer when ``DATABASE_URL`` is set. The
SQS SLA-timer worker (``app_platform/workers/sla_timer_worker.py``) is
what actually wakes the thread after the first-reminder / escalation
delay. In tests we use the in-memory MemorySaver and drive the loop
synchronously.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.time_anomaly.nodes import (
    ROUTE_CLOSE,
    ROUTE_END,
    ROUTE_ESCALATE,
    ROUTE_OUTREACH,
    ROUTE_WAIT,
    close_node,
    detect_node,
    escalate_hitl_node,
    outreach_node,
    wait_recheck_node,
)
from src.agents.time_anomaly.state import TimeAnomalyAlertState

logger = logging.getLogger(__name__)


def _route_from_detect(state: TimeAnomalyAlertState) -> str:
    nxt = state.get("next")
    if nxt == ROUTE_OUTREACH:
        return "outreach"
    return ROUTE_END


def _route_from_outreach(state: TimeAnomalyAlertState) -> str:
    nxt = state.get("next")
    if nxt == ROUTE_WAIT:
        return "wait_recheck"
    if nxt == ROUTE_ESCALATE:
        return "escalate_hitl"
    return ROUTE_END


def _route_from_wait(state: TimeAnomalyAlertState) -> str:
    nxt = state.get("next")
    if nxt == ROUTE_CLOSE:
        return "close"
    if nxt == ROUTE_ESCALATE:
        return "escalate_hitl"
    return ROUTE_END


def _build_graph() -> StateGraph:
    graph = StateGraph(TimeAnomalyAlertState)
    graph.add_node("detect", detect_node)
    graph.add_node("outreach", outreach_node)
    graph.add_node("wait_recheck", wait_recheck_node)
    graph.add_node("escalate_hitl", escalate_hitl_node)
    graph.add_node("close", close_node)

    graph.set_entry_point("detect")
    graph.add_conditional_edges(
        "detect",
        _route_from_detect,
        {"outreach": "outreach", ROUTE_END: END},
    )
    graph.add_conditional_edges(
        "outreach",
        _route_from_outreach,
        {
            "wait_recheck": "wait_recheck",
            "escalate_hitl": "escalate_hitl",
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        "wait_recheck",
        _route_from_wait,
        {
            "close": "close",
            "escalate_hitl": "escalate_hitl",
            ROUTE_END: END,
        },
    )
    graph.add_edge("close", END)
    graph.add_edge("escalate_hitl", END)
    return graph


def _get_checkpointer() -> Any | None:
    """Return a Postgres checkpointer when DATABASE_URL is set + the
    optional langgraph postgres extra is installed, else None.

    Returning ``None`` lets callers fall back to ``MemorySaver`` or
    simply compile without persistence (useful for unit tests and dry
    runs). The production deployment sets DATABASE_URL and installs
    ``langgraph[postgres]`` so this path activates.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError:
        logger.warning(
            "langgraph.checkpoint.postgres not installed; "
            "Time Anomaly agent running without durable checkpointing. "
            "Install langgraph[postgres] for production."
        )
        return None

    return AsyncPostgresSaver.from_conn_string(db_url)


def get_graph(checkpointer: Any | None = None) -> Any:
    """Compile and return the Time Anomaly Agent graph.

    Callers can pass an explicit checkpointer (tests typically pass
    ``MemorySaver()`` for in-process runs). When *checkpointer* is
    ``None``, the function tries to build a Postgres saver from env and
    falls back to compiling without a checkpointer if one isn't
    available.
    """
    graph = _build_graph()
    saver = checkpointer or _get_checkpointer()
    if saver is None:
        return graph.compile()
    return graph.compile(checkpointer=saver)
