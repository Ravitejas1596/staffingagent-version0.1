"""
VMS Reconciliation Agent — reconcile VMS (e.g. B4Health) vs ATS/CRM (Bullhorn).
Reduces unbilled backlog; human-in-the-loop for low-confidence matches.
"""
import json
import re
from typing import Any

from langgraph.graph import END, StateGraph

import asyncio

from src.agents.vms_reconciliation.prompts import VMS_RECONCILIATION_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import VMSReconciliationState, as_dict


def analyze_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run Claude to propose VMS ↔ ATS matches."""
    state = as_dict(state)
    vms = state.get("vms_records") or []
    ats = state.get("ats_records") or []
    if not vms and not ats:
        return {
            "result": {"error": "No vms_records or ats_records in state"},
            "error": "No input records",
        }
    user_content = (
        f"Reconcile these records.\n\nVMS records ({len(vms)}):\n{json.dumps(vms[:50], default=str)}\n\n"
        f"ATS records ({len(ats)}):\n{json.dumps(ats[:50], default=str)}\n\n"
        "Return only a single JSON object with keys: proposed_matches, unmatched_vms, unmatched_ats, human_review_required, summary."
    )
    messages = [{"role": "user", "content": user_content}]
    try:
        content, usage = asyncio.get_event_loop().run_until_complete(invoke_llm(
            messages,
            task_type="structured_matching",
            system=VMS_RECONCILIATION_SYSTEM,
            tenant_id=state.get("tenant_id"),
        ))
    except Exception:
        try:
            content, usage = invoke_claude(
                messages,
                system=VMS_RECONCILIATION_SYSTEM,
            )
        except Exception as e:
            return {"error": str(e), "result": None}
    # Parse JSON from response (handle markdown code blocks)
    text = content.strip()
    for pattern in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            text = m.group(1).strip()
            break
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        out = {"summary": content, "human_review_required": True, "proposed_matches": [], "unmatched_vms": [], "unmatched_ats": []}
    prior = state.get("token_usage") or []
    return {
        "proposed_matches": out.get("proposed_matches", []),
        "unmatched_vms": out.get("unmatched_vms", []),
        "unmatched_ats": out.get("unmatched_ats", []),
        "human_review_required": out.get("human_review_required", False),
        "result": out,
        **usage_update(usage, prior),
    }


def human_review_node(state: dict[str, Any]) -> dict[str, Any]:
    """HITL: human approves/rejects proposed matches. Placeholder — in prod, wait for UI input."""
    state = as_dict(state)
    return {"human_review_required": True, "result": state.get("result")}


def get_graph():
    """Build and return compiled VMS Reconciliation graph."""
    graph = StateGraph(VMSReconciliationState)
    graph.add_node("analyze", analyze_node)
    graph.add_node("human_review", human_review_node)
    graph.set_entry_point("analyze")
    graph.add_conditional_edges("analyze", _route_after_analyze, ["human_review", "__end__"])
    graph.add_edge("human_review", END)
    return graph.compile()


def _route_after_analyze(state: dict[str, Any]) -> str:
    s = as_dict(state)
    if s.get("human_review_required"):
        return "human_review"
    return "__end__"
