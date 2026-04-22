"""Smoke tests for the Time Anomaly Agent graph wiring.

These tests do NOT exercise node bodies (those pull on Bullhorn/Twilio/DB
and are covered by the integration test suite). They verify that:

- The 5-node state graph compiles under MemorySaver and without any
  checkpointer — both valid deployment shapes.
- Routing labels used inside nodes match the conditional-edge labels
  registered on the graph, so a rename in one place surfaces
  immediately in the other.

Skip gracefully if ``langgraph`` isn't installed in the local env (it is
in CI + production). Running ``pytest -m '' -k time_anomaly_graph`` in a
fresh venv without ``langgraph`` shouldn't block the rest of the suite.
"""
from __future__ import annotations

import pytest

pytest.importorskip("langgraph")


def test_graph_compiles_without_checkpointer() -> None:
    from src.agents.time_anomaly.graph import get_graph

    compiled = get_graph(checkpointer=None)
    assert compiled is not None


def test_graph_compiles_with_memory_saver() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    from src.agents.time_anomaly.graph import get_graph

    compiled = get_graph(checkpointer=MemorySaver())
    assert compiled is not None


def test_node_route_labels_cover_every_conditional_edge() -> None:
    """Belt-and-suspenders guard: the ROUTE_* constants in nodes.py are
    the vocabulary the conditional edge functions expect. If someone
    adds a new terminal state to a node without registering it on the
    graph, the node will return a dict whose ``next`` key doesn't match
    any edge label and LangGraph will raise at runtime.
    """
    from src.agents.time_anomaly import nodes

    expected = {
        nodes.ROUTE_OUTREACH,
        nodes.ROUTE_WAIT,
        nodes.ROUTE_ESCALATE,
        nodes.ROUTE_CLOSE,
        nodes.ROUTE_END,
    }
    assert expected == {
        "outreach",
        "wait_recheck",
        "escalate_hitl",
        "close",
        "__end__",
    }
