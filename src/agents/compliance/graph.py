"""Compliance Agent — production-grade deterministic + LLM compliance monitoring.

Graph shape:
    scan ─┬── classify ── alert_hitl ── end  (violations found)
          └── end                             (all clear)

Deterministic checks run first (credential expiry, OT classification,
contract terms, worker classification). LLM is used only for ambiguous
classification cases that require reasoning.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.compliance.detectors import (
    ComplianceViolation,
    check_contract_terms,
    check_credential_expiry,
    check_overtime_classification,
    check_worker_classification,
)
from src.agents.compliance.prompts import COMPLIANCE_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import ComplianceState, as_dict

logger = logging.getLogger(__name__)


def _violation_to_dict(v: ComplianceViolation) -> dict[str, Any]:
    return {
        "violation_type": v.violation_type,
        "severity": v.severity,
        "description": v.description,
        "entity_type": v.entity_type,
        "entity_id": v.entity_id,
        "entity_name": v.entity_name,
        "recommended_action": v.recommended_action,
        "details": v.details,
    }


def scan_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run all deterministic compliance checks."""
    state = as_dict(state)
    placements = state.get("activity_log") or state.get("placements") or []
    credentials = state.get("policies") or state.get("credentials") or []
    cfg = state.get("config_overrides") or {}

    if not placements and not credentials:
        return {"result": {"error": "No data to scan"}, "error": "No input"}

    all_violations: list[dict[str, Any]] = []

    # Credential expiry
    if credentials:
        for v in check_credential_expiry(
            credentials,
            warning_days=int(cfg.get("credential_expiry_warning_days", 30)),
            critical_days=int(cfg.get("credential_expiry_critical_days", 7)),
        ):
            all_violations.append(_violation_to_dict(v))

    # Placement-level checks
    if placements:
        for v in check_overtime_classification(
            placements,
            ot_threshold_hours=float(cfg.get("overtime_weekly_threshold_hours", 40.0)),
        ):
            all_violations.append(_violation_to_dict(v))

        for v in check_contract_terms(placements):
            all_violations.append(_violation_to_dict(v))

        for v in check_worker_classification(placements):
            all_violations.append(_violation_to_dict(v))

    by_type = {}
    by_severity = {}
    for v in all_violations:
        by_type[v["violation_type"]] = by_type.get(v["violation_type"], 0) + 1
        by_severity[v["severity"]] = by_severity.get(v["severity"], 0) + 1

    has_violations = len(all_violations) > 0
    summary = f"Scanned {len(placements)} placements + {len(credentials)} credentials — {len(all_violations)} violations"
    logger.info("compliance.scan: %s", summary)

    return {
        "violations": all_violations,
        "human_review_required": has_violations,
        "result": {
            "violations": all_violations,
            "violation_count": len(all_violations),
            "by_type": by_type,
            "by_severity": by_severity,
            "summary": summary,
        },
    }


def _extract_json(content: str) -> str:
    text = content.strip()
    for pat in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text


def classify_node(state: dict[str, Any]) -> dict[str, Any]:
    """LLM-assisted classification for ambiguous compliance cases.

    Takes the violations from scan_node and asks the LLM to:
    1. Validate severity assessment
    2. Identify any false positives
    3. Suggest specific remediation steps
    """
    state = as_dict(state)
    violations = state.get("violations") or []
    prior_usage = state.get("token_usage") or []

    if not violations:
        return {"recommended_actions": [], **usage_update(None, prior_usage)}

    user_content = (
        f"Review {len(violations)} compliance violations and provide analysis.\n\n"
        f"Violations:\n{json.dumps(violations[:20], default=str)}\n\n"
        f"For each violation, assess:\n"
        f"1. Is the severity appropriate?\n"
        f"2. Could this be a false positive?\n"
        f"3. What specific remediation steps are needed?\n\n"
        f"Return JSON: {{\"assessments\": [{{\"violation_type\": ..., \"entity_id\": ..., "
        f"\"adjusted_severity\": ..., \"false_positive_risk\": \"low|medium|high\", "
        f"\"remediation_steps\": [...]}}]}}"
    )

    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(invoke_llm(
            [{"role": "user", "content": user_content}],
            task_type="reasoning",
            system=COMPLIANCE_SYSTEM,
            tenant_id=state.get("tenant_id"),
        ))
    except Exception:
        try:
            content, usage = invoke_claude(
                [{"role": "user", "content": user_content}],
                system=COMPLIANCE_SYSTEM,
            )
        except Exception as e:
            return {"error": str(e), "recommended_actions": [], **usage_update(None, prior_usage)}

    text = _extract_json(content)
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        out = {"assessments": []}

    actions = out.get("assessments", [])
    return {
        "recommended_actions": actions,
        **usage_update(usage, prior_usage),
    }


def alert_hitl_node(state: dict[str, Any]) -> dict[str, Any]:
    """HITL gate — compliance violations require human review before action."""
    state = as_dict(state)
    result = state.get("result") or {}
    actions = state.get("recommended_actions") or []

    return {
        "human_review_required": True,
        "result": {
            **result,
            "recommended_actions": actions,
            "awaiting_review": True,
        },
    }


def _route_after_scan(state: dict[str, Any]) -> str:
    s = as_dict(state)
    if s.get("human_review_required"):
        return "classify"
    return "__end__"


def get_graph():
    """Build and return compiled Compliance Agent graph."""
    graph = StateGraph(ComplianceState)
    graph.add_node("scan", scan_node)
    graph.add_node("classify", classify_node)
    graph.add_node("alert_hitl", alert_hitl_node)
    graph.set_entry_point("scan")
    graph.add_conditional_edges(
        "scan",
        _route_after_scan,
        ["classify", "__end__"],
    )
    graph.add_edge("classify", "alert_hitl")
    graph.add_edge("alert_hitl", END)
    return graph.compile()
