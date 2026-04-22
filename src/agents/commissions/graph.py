"""Commissions Agent — 3-node LangGraph pipeline."""
from __future__ import annotations
import json, logging, re
from typing import Any
from langgraph.graph import END, StateGraph
from src.agents.commissions.calculators import calculate_placements_commissions
from src.agents.commissions.prompts import COMMISSIONS_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import as_dict
from src.agents.commissions.state import CommissionsState
from src.agents.commissions.config import CommissionsConfig

logger = logging.getLogger(__name__)

def compute_commissions_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    placements = state.get("placements") or []
    if not placements: return {"result": {"error": "No placements data"}, "error": "No input"}
    cfg = state.get("config_overrides") or {}
    config_obj = CommissionsConfig(**cfg) if cfg else CommissionsConfig()
    results = calculate_placements_commissions(placements, config_obj)
    return {"commissions": results}

def validate_commissions_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    commissions = state.get("commissions") or []
    prior = state.get("token_usage") or []
    if not commissions: return {**usage_update(None, prior)}
    
    user = (f"Review these commission calculations and check for errors or split-commissions cases:\n\n"
            f"{json.dumps(commissions[:20], default=str)}\n\n"
            f"Provide validation results and any adjustments in JSON.")
    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(
            invoke_llm([{"role": "user", "content": user}], task_type="reasoning",
                       system=COMMISSIONS_SYSTEM, tenant_id=state.get("tenant_id")))
    except Exception:
        try:
            content, usage = invoke_claude([{"role": "user", "content": user}], system=COMMISSIONS_SYSTEM)
        except Exception as e:
            return {"error": str(e), **usage_update(None, prior)}
    text = content.strip()
    for pat in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m: text = m.group(1).strip(); break
    try: out = json.loads(text)
    except json.JSONDecodeError: out = {"validation_results": {}}
    return {"validation_results": out, **usage_update(usage, prior)}

def report_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    commissions = state.get("commissions") or []
    valid = state.get("validation_results") or {}
    total = sum(sum(c["amount"] for c in p["commissions"]) for p in commissions)
    return {"result": {"commissions": commissions, "validation": valid, "total_commission": round(total, 2), "summary": f"Calculated ${total:,.2f} in commissions across {len(commissions)} placements."}}

def get_graph():
    graph = StateGraph(CommissionsState)
    graph.add_node("compute_commissions", compute_commissions_node)
    graph.add_node("validate_commissions", validate_commissions_node)
    graph.add_node("report", report_node)
    graph.set_entry_point("compute_commissions")
    graph.add_edge("compute_commissions", "validate_commissions")
    graph.add_edge("validate_commissions", "report")
    graph.add_edge("report", END)
    return graph.compile()
