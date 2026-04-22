"""Invoice Matching Agent — production-grade deterministic + LLM matching.

Graph shape:
    match ─┬── validate ── persist ── end  (matches found)
           └── end                          (nothing to match)

Deterministic matching runs first (client + amount + date). LLM handles
ambiguous multi-line invoice matching. Exceptions are always flagged
for HITL review.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.invoice_matching.detectors import (
    InvoiceException,
    InvoiceMatch,
    detect_duplicate_invoices,
    match_invoices_to_charges,
)
from src.agents.invoice_matching.prompts import INVOICE_MATCHING_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import InvoiceMatchingState, as_dict

logger = logging.getLogger(__name__)


def _match_to_dict(m: InvoiceMatch) -> dict[str, Any]:
    return {
        "invoice_id": m.invoice_id,
        "charge_id": m.charge_id,
        "client_name": m.client_name,
        "confidence": m.confidence,
        "match_method": m.match_method,
        "amount_delta": m.amount_delta,
        "details": m.details,
    }


def _exception_to_dict(e: InvoiceException) -> dict[str, Any]:
    return {
        "exception_type": e.exception_type,
        "severity": e.severity,
        "description": e.description,
        "invoice_id": e.invoice_id,
        "charge_id": e.charge_id,
        "client_name": e.client_name,
        "financial_impact": e.financial_impact,
        "details": e.details,
    }


def _extract_json(content: str) -> str:
    text = content.strip()
    for pat in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text


def match_node(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic invoice-to-charge matching."""
    state = as_dict(state)
    invoices = state.get("invoices") or []
    charges = state.get("purchase_orders") or []
    cfg = state.get("config_overrides") or {}

    if not invoices and not charges:
        return {"result": {"error": "No invoices or charges"}, "error": "No input"}

    matches, exceptions = match_invoices_to_charges(
        invoices, charges,
        amount_tolerance_pct=float(cfg.get("amount_tolerance_pct", 2.0)),
        max_days_gap=int(cfg.get("max_days_between_invoice_and_po", 90)),
    )

    # Also check for duplicate invoices
    dup_exceptions = detect_duplicate_invoices(invoices)
    all_exceptions = [_exception_to_dict(e) for e in exceptions + dup_exceptions]

    match_dicts = [_match_to_dict(m) for m in matches]
    has_issues = len(all_exceptions) > 0

    by_method = {}
    for m in matches:
        by_method[m.match_method] = by_method.get(m.match_method, 0) + 1

    total_delta = sum(abs(m.amount_delta) for m in matches)
    summary = (
        f"Matched {len(matches)}/{len(invoices)} invoices, "
        f"{len(all_exceptions)} exceptions, "
        f"${total_delta:,.2f} total variance"
    )
    logger.info("invoice_matching.match: %s", summary)

    return {
        "proposed_matches": match_dicts,
        "exceptions": all_exceptions,
        "human_review_required": has_issues,
        "result": {
            "proposed_matches": match_dicts,
            "exceptions": all_exceptions,
            "match_count": len(matches),
            "exception_count": len(all_exceptions),
            "by_method": by_method,
            "total_variance": total_delta,
            "summary": summary,
        },
    }


def validate_node(state: dict[str, Any]) -> dict[str, Any]:
    """LLM-assisted validation for complex matching scenarios.

    Reviews exceptions and low-confidence matches for potential
    resolutions the deterministic matcher couldn't handle.
    """
    state = as_dict(state)
    exceptions = state.get("exceptions") or []
    prior_usage = state.get("token_usage") or []

    if not exceptions:
        return {"recommended_actions": [], **usage_update(None, prior_usage)}

    user_content = (
        f"Review {len(exceptions)} invoice matching exceptions.\n\n"
        f"Exceptions:\n{json.dumps(exceptions[:20], default=str)}\n\n"
        f"For each, determine:\n"
        f"1. Root cause (data entry error, timing, legitimate difference)\n"
        f"2. Recommended resolution\n"
        f"3. Priority (critical/high/medium/low)\n\n"
        f"Return JSON: {{\"assessments\": [{{\"exception_type\": ..., "
        f"\"invoice_id\": ..., \"root_cause\": ..., \"resolution\": ..., "
        f"\"priority\": ...}}]}}"
    )

    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(invoke_llm(
            [{"role": "user", "content": user_content}],
            task_type="structured_extraction",
            system=INVOICE_MATCHING_SYSTEM,
            tenant_id=state.get("tenant_id"),
        ))
    except Exception:
        try:
            content, usage = invoke_claude(
                [{"role": "user", "content": user_content}],
                system=INVOICE_MATCHING_SYSTEM,
            )
        except Exception as e:
            return {"error": str(e), **usage_update(None, prior_usage)}

    text = _extract_json(content)
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        out = {"assessments": []}

    return {
        "recommended_actions": out.get("assessments", []),
        **usage_update(usage, prior_usage),
    }


def persist_node(state: dict[str, Any]) -> dict[str, Any]:
    """Finalize results and prepare for HITL review.

    In production, this writes match records to the database.
    Matches above auto_approve_confidence are auto-approved;
    the rest go to the review queue.
    """
    state = as_dict(state)
    matches = state.get("proposed_matches") or []
    exceptions = state.get("exceptions") or []
    actions = state.get("recommended_actions") or []
    cfg = state.get("config_overrides") or {}

    auto_threshold = float(cfg.get("auto_approve_confidence", 0.95))
    review_threshold = float(cfg.get("review_confidence", 0.70))

    auto_approved = [m for m in matches if m.get("confidence", 0) >= auto_threshold]
    needs_review = [m for m in matches if review_threshold <= m.get("confidence", 0) < auto_threshold]
    low_confidence = [m for m in matches if m.get("confidence", 0) < review_threshold]

    result = state.get("result") or {}
    return {
        "human_review_required": len(needs_review) > 0 or len(exceptions) > 0,
        "result": {
            **result,
            "auto_approved": len(auto_approved),
            "needs_review": len(needs_review),
            "low_confidence": len(low_confidence),
            "recommended_actions": actions,
        },
    }


def _route_after_match(state: dict[str, Any]) -> str:
    s = as_dict(state)
    if s.get("human_review_required"):
        return "validate"
    return "__end__"


def get_graph():
    """Build and return compiled Invoice Matching Agent graph."""
    graph = StateGraph(InvoiceMatchingState)
    graph.add_node("match", match_node)
    graph.add_node("validate", validate_node)
    graph.add_node("persist", persist_node)
    graph.set_entry_point("match")
    graph.add_conditional_edges(
        "match",
        _route_after_match,
        ["validate", "__end__"],
    )
    graph.add_edge("validate", "persist")
    graph.add_edge("persist", END)
    return graph.compile()
