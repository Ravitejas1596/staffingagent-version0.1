"""Risk Alert Agent — production-grade deterministic risk detection.

Monitors placements and charges for rate, markup, amount, hours, and
duplicate risks. No LLM required for structured placement data. HITL
gate for high-severity violations.

Graph shape:
    analyze ─┬── end          (no risks or all low-severity)
             └── human_review ── end
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langgraph.graph import END, StateGraph

from src.agents.risk_alert.config import RiskAlertConfig, load_config
from src.agents.risk_alert.detectors import (
    RiskCandidate,
    detect_amount_anomalies,
    detect_duplicate_charges,
    detect_hours_mismatches,
    detect_markup_violations,
    detect_placement_mismatches,
    detect_rate_violations,
)
from src.shared.state import AgentState, as_dict

logger = logging.getLogger(__name__)


class RiskAlertState(AgentState):
    """State for the risk alert agent."""
    placements: list[dict[str, Any]] = []
    charges: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    recommended_actions: list[dict[str, Any]] = []


def _candidate_to_dict(c: RiskCandidate) -> dict[str, Any]:
    """Convert a detector result to serializable dict for state."""
    return {
        "risk_type": c.risk_type,
        "severity": c.severity,
        "description": c.description,
        "placement_id": c.placement_id,
        "candidate_name": c.candidate_name,
        "financial_impact": c.financial_impact,
        "details": c.details,
    }


def analyze_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run all deterministic risk detectors against placement and charge data.

    Loads per-tenant config from the database, runs each detector category,
    and collects all risk candidates into a unified list. No LLM calls.
    """
    state = as_dict(state)
    placements = state.get("placements") or []
    charges = state.get("charges") or []
    if not placements and not charges:
        return {"result": {"error": "No placements or charges"}, "error": "No input"}

    # Use inline config (already loaded by caller or defaults)
    cfg = RiskAlertConfig()
    cfg_overrides = state.get("config_overrides")
    if isinstance(cfg_overrides, dict):
        from src.agents.risk_alert.config import _apply_override
        for k, v in cfg_overrides.items():
            cfg = _apply_override(cfg, k, v)

    all_risks: list[dict[str, Any]] = []

    # ── Placement-level checks ──────────────────────────────────
    if placements:
        for c in detect_placement_mismatches(
            placements,
            approved_statuses=cfg.approved_statuses,
            inactive_statuses=cfg.inactive_statuses,
        ):
            all_risks.append(_candidate_to_dict(c))

        for c in detect_rate_violations(
            placements,
            federal_min_wage=cfg.minimum_wage,
            high_pay_rate=cfg.high_pay_rate,
            high_bill_rate=cfg.high_bill_rate,
            state_wage_overrides=cfg.state_min_wage_overrides or None,
        ):
            all_risks.append(_candidate_to_dict(c))

        for c in detect_markup_violations(
            placements,
            low_markup_pct=cfg.low_markup_pct,
            high_markup_pct=cfg.high_markup_pct,
        ):
            all_risks.append(_candidate_to_dict(c))

    # ── Charge-level checks ─────────────────────────────────────
    if charges:
        for c in detect_amount_anomalies(
            charges,
            high_pay_amount=cfg.high_pay_amount,
            high_bill_amount=cfg.high_bill_amount,
        ):
            all_risks.append(_candidate_to_dict(c))

        for c in detect_hours_mismatches(
            charges,
            bill_rate_mismatch_pct=cfg.bill_rate_mismatch_pct,
        ):
            all_risks.append(_candidate_to_dict(c))

        for c in detect_duplicate_charges(charges):
            all_risks.append(_candidate_to_dict(c))

    human_review = any(r["severity"] == "high" for r in all_risks)

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for r in all_risks:
        by_type[r["risk_type"]] = by_type.get(r["risk_type"], 0) + 1
        by_severity[r["severity"]] = by_severity.get(r["severity"], 0) + 1

    summary = (
        f"Analyzed {len(placements)} placements + {len(charges)} charges, "
        f"found {len(all_risks)} risk items"
    )
    logger.info("risk_alert.analyze: %s", summary)

    return {
        "risks": all_risks,
        "human_review_required": human_review,
        "result": {
            "risks": all_risks,
            "risk_count": len(all_risks),
            "by_type": by_type,
            "by_severity": by_severity,
            "human_review_required": human_review,
            "summary": summary,
        },
    }


def human_review_node(state: dict[str, Any]) -> dict[str, Any]:
    """HITL gate — alert is queued for human review.

    In production, the AlertQueue UI picks up the alert. The agent
    run transitions to ``completed`` after this node; resolution
    happens asynchronously via the PATCH /api/alerts/{id}/review
    endpoint.
    """
    state = as_dict(state)
    result = state.get("result") or {}
    risks = state.get("risks") or []

    # Generate recommended actions for each risk
    actions: list[dict[str, Any]] = []
    action_map = {
        "below_federal_min_wage": "Escalate to compliance team — potential FLSA violation",
        "below_state_min_wage": "Escalate to compliance team — state minimum wage violation",
        "negative_markup": "Review rate configuration — loss on placement",
        "high_pay_rate": "Verify rate against placement contract",
        "high_bill_rate": "Verify bill rate against client MSA",
        "low_markup": "Review pricing strategy — margin below target",
        "high_markup": "Verify bill rate — potential client billing error",
        "high_pay_amount": "Verify hours worked — unusually high pay charge",
        "high_bill_amount": "Verify hours worked — unusually high bill charge",
        "negative_pay_amount": "Investigate — pay amount should not be negative",
        "negative_bill_amount": "Investigate — bill amount should not be negative",
        "pay_no_bill": "Create corresponding billable charge or investigate",
        "bill_no_pay": "Create corresponding payable charge or investigate",
        "pay_bill_hours_mismatch": "Reconcile pay and bill hours for this period",
        "pay_rate_card_mismatch": "Verify transaction rate matches placement rate card",
        "bill_rate_card_mismatch": "Verify transaction rate matches placement rate card",
        "duplicate_charge": "Review and void duplicate charge(s)",
        "active_placement_date_mismatch": "Update placement end date or change status",
        "inactive_placement_date_mismatch": "Update placement status or correct end date",
    }
    for r in risks:
        actions.append({
            "risk_type": r.get("risk_type"),
            "placement_id": r.get("placement_id"),
            "recommended_action": action_map.get(r.get("risk_type", ""), "Review manually"),
        })

    return {
        "human_review_required": True,
        "recommended_actions": actions,
        "result": {**result, "recommended_actions": actions},
    }


def get_graph():
    """Build and return compiled Risk Alert graph."""
    graph = StateGraph(RiskAlertState)
    graph.add_node("analyze", analyze_node)
    graph.add_node("human_review", human_review_node)
    graph.set_entry_point("analyze")
    graph.add_conditional_edges(
        "analyze",
        lambda s: "human_review" if as_dict(s).get("human_review_required") else "__end__",
        ["human_review", "__end__"],
    )
    graph.add_edge("human_review", END)
    return graph.compile()
