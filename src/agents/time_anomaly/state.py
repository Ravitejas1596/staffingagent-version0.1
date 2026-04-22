"""State model for the Time Anomaly Agent v1 state machine.

Each agent invocation processes exactly one placement/pay-period pair.
The LangGraph state object carries everything the five nodes (detect,
outreach, wait_recheck, escalate_hitl, close) need to coordinate without
reaching into the DB between hops.

This is deliberately separate from ``src.shared.state.TimeAnomalyState``
— that older Pydantic model served the single-shot LLM classifier and
is kept for backward compatibility during migration. New code uses the
typed dict below because LangGraph's Postgres checkpointer serializes
TypedDicts more cleanly than Pydantic BaseModels across versions.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, TypedDict


AlertState = Literal[
    "detected", "outreach_sent", "wait_recheck", "escalated_hitl", "resolved"
]

Resolution = Literal[
    "employee_corrected",
    "hitl_resolved",
    "excluded",
    "dismissed_false_positive",
]


class TimeAnomalyAlertState(TypedDict, total=False):
    """State machine state. Every key is optional so partial updates
    from nodes are welcome — LangGraph merges the returned partial into
    the running state object.
    """

    # ── inputs (populated by the caller) ────────────────────────
    tenant_id: str
    placement_id: str
    candidate_id: str | None
    bullhorn_placement_id: str
    bullhorn_candidate_id: str | None
    pay_period_start: date
    pay_period_end: date
    dry_run: bool
    agent_run_id: str | None

    # ── detect node outputs ─────────────────────────────────────
    current_timesheet: dict[str, Any] | None
    alert_candidate: dict[str, Any] | None
    alert_id: str | None
    detected_at: datetime | None

    # ── outreach node outputs ───────────────────────────────────
    sms_sid: str | None
    sms_skipped_reason: str | None
    bte_link_url: str | None
    rendered_body: str | None

    # ── wait_recheck outputs ────────────────────────────────────
    recheck_timesheet: dict[str, Any] | None
    sla_timer_id: str | None

    # ── escalation / close ──────────────────────────────────────
    final_state: AlertState | None
    resolution: Resolution | None
    error: str | None
