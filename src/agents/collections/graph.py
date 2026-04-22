"""Collections Agent — production-grade AR prioritization + LLM draft outreach.

Graph shape:
    prioritize ─┬── draft_outreach ── review_hitl ── end
                └── end (nothing actionable)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.collections.detectors import ARPriority, group_by_client, prioritize_ar
from src.agents.collections.prompts import COLLECTIONS_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import CollectionsState, as_dict

logger = logging.getLogger(__name__)


def _extract_json(content: str) -> str:
    text = content.strip()
    for pat in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text


def _priority_to_dict(p: ARPriority) -> dict[str, Any]:
    return {
        "invoice_id": p.invoice_id,
        "client_name": p.client_name,
        "amount": p.amount,
        "days_outstanding": p.days_outstanding,
        "priority_score": p.priority_score,
        "priority_tier": p.priority_tier,
        "escalation_stage": p.escalation_stage,
        "recommended_action": p.recommended_action,
        "details": p.details,
    }


def prioritize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic AR prioritization — no LLM needed."""
    state = as_dict(state)
    ar = state.get("ar_aging") or []
    if not ar:
        return {"result": {"error": "No ar_aging"}, "error": "No input"}

    # Load config overrides from state
    cfg = state.get("config_overrides") or {}

    priorities = prioritize_ar(
        ar,
        reminder_days=int(cfg.get("reminder_days", 15)),
        followup_days=int(cfg.get("followup_days", 30)),
        escalation_days=int(cfg.get("escalation_days", 60)),
        legal_days=int(cfg.get("legal_escalation_days", 90)),
        high_priority_amount=float(cfg.get("high_priority_amount", 10000.0)),
        critical_priority_amount=float(cfg.get("critical_priority_amount", 50000.0)),
    )

    priority_dicts = [_priority_to_dict(p) for p in priorities]
    actionable = [p for p in priorities if p.escalation_stage != "reminder" or p.priority_tier in ("high", "critical")]

    by_tier = {}
    for p in priorities:
        by_tier[p.priority_tier] = by_tier.get(p.priority_tier, 0) + 1

    by_stage = {}
    for p in priorities:
        by_stage[p.escalation_stage] = by_stage.get(p.escalation_stage, 0) + 1

    total_at_risk = sum(p.amount for p in priorities)
    summary = (
        f"Prioritized {len(priorities)} AR items — "
        f"${total_at_risk:,.0f} total outstanding, "
        f"{len(actionable)} actionable"
    )
    logger.info("collections.prioritize: %s", summary)

    return {
        "prioritization": priority_dicts,
        "suggested_actions": [_priority_to_dict(p) for p in actionable],
        "human_review_required": len(actionable) > 0,
        "result": {
            "prioritization": priority_dicts,
            "by_tier": by_tier,
            "by_stage": by_stage,
            "total_at_risk": total_at_risk,
            "actionable_count": len(actionable),
            "summary": summary,
        },
    }


def draft_outreach_node(state: dict[str, Any]) -> dict[str, Any]:
    """LLM-powered draft message generation for collection outreach.

    Groups actionable items by client and generates tailored messages
    using tone calibration based on aging tier.
    """
    state = as_dict(state)
    actionable = state.get("suggested_actions") or []
    prior_usage = state.get("token_usage") or []

    if not actionable:
        return {"draft_messages": [], **usage_update(None, prior_usage)}

    # Group by client for batch outreach
    by_client: dict[str, list[dict]] = {}
    for item in actionable[:20]:  # Cap to manage token usage
        client = item.get("client_name", "Unknown")
        by_client.setdefault(client, []).append(item)

    user_content = (
        f"Draft collection outreach messages for {len(by_client)} clients.\n\n"
        f"Group items by client and generate ONE professional message per client.\n"
        f"Adjust tone based on escalation_stage: reminder=friendly, follow_up=firm, "
        f"escalation=urgent, legal=formal demand.\n\n"
        f"Client AR items:\n{json.dumps(by_client, default=str)}\n\n"
        f"Return JSON: {{\"draft_messages\": [{{\"client_name\": ..., \"subject\": ..., "
        f"\"body\": ..., \"tone\": ..., \"total_outstanding\": ...}}]}}"
    )

    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(invoke_llm(
            [{"role": "user", "content": user_content}],
            task_type="reasoning",
            system=COLLECTIONS_SYSTEM,
            tenant_id=state.get("tenant_id"),
        ))
    except Exception:
        try:
            content, usage = invoke_claude(
                [{"role": "user", "content": user_content}],
                system=COLLECTIONS_SYSTEM,
            )
        except Exception as e:
            return {"error": str(e), "draft_messages": [], **usage_update(None, prior_usage)}

    text = _extract_json(content)
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        out = {"draft_messages": []}

    drafts = out.get("draft_messages", [])
    logger.info("collections.draft_outreach: generated %d draft messages", len(drafts))

    return {
        "draft_messages": drafts,
        **usage_update(usage, prior_usage),
    }


def review_hitl_node(state: dict[str, Any]) -> dict[str, Any]:
    """HITL gate — human reviews prioritization + draft messages before send.

    In production, the AlertQueue UI picks up the review. No messages
    are sent until explicit human approval.
    """
    state = as_dict(state)
    result = state.get("result") or {}
    drafts = state.get("draft_messages") or []

    return {
        "human_review_required": True,
        "result": {
            **result,
            "draft_messages": drafts,
            "awaiting_review": True,
        },
    }


def _route_after_prioritize(state: dict[str, Any]) -> str:
    s = as_dict(state)
    if s.get("human_review_required"):
        return "draft_outreach"
    return "__end__"


def get_graph():
    """Build and return compiled Collections Agent graph."""
    graph = StateGraph(CollectionsState)
    graph.add_node("prioritize", prioritize_node)
    graph.add_node("draft_outreach", draft_outreach_node)
    graph.add_node("review_hitl", review_hitl_node)
    graph.set_entry_point("prioritize")
    graph.add_conditional_edges(
        "prioritize",
        _route_after_prioritize,
        ["draft_outreach", "__end__"],
    )
    graph.add_edge("draft_outreach", "review_hitl")
    graph.add_edge("review_hitl", END)
    return graph.compile()
