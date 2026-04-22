"""GL Reconciliation Agent — 3-node LangGraph pipeline.

    extract_match → flag_discrepancies → report
"""
from __future__ import annotations
import json, logging, re
from typing import Any
from langgraph.graph import END, StateGraph
from src.agents.gl_reconciliation.detectors import reconcile_gl_to_charges, GLDiscrepancy
from src.agents.gl_reconciliation.prompts import GL_RECONCILIATION_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import AgentState, as_dict

logger = logging.getLogger(__name__)

class GLReconciliationState(AgentState):
    gl_entries: list[dict[str, Any]] = []
    charges: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    discrepancies: list[dict[str, Any]] = []

def _disc_to_dict(d: GLDiscrepancy) -> dict[str, Any]:
    return {"discrepancy_type": d.discrepancy_type, "severity": d.severity,
            "description": d.description, "gl_entry_id": d.gl_entry_id,
            "charge_id": d.charge_id, "financial_impact": d.financial_impact,
            "details": d.details}

def extract_match_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    gl = state.get("gl_entries") or []
    charges = state.get("charges") or []
    if not gl and not charges:
        return {"result": {"error": "No GL entries or charges"}, "error": "No input"}
    cfg = state.get("config_overrides") or {}
    matches, discs = reconcile_gl_to_charges(
        gl, charges, amount_tolerance_pct=float(cfg.get("amount_tolerance_pct", 1.0)))
    disc_dicts = [_disc_to_dict(d) for d in discs]
    by_type = {}
    for d in discs:
        by_type[d.discrepancy_type] = by_type.get(d.discrepancy_type, 0) + 1
    total_impact = sum(abs(d.financial_impact or 0) for d in discs)
    summary = f"Matched {len(matches)}/{len(gl)} GL entries, {len(discs)} discrepancies, ${total_impact:,.2f} total impact"
    logger.info("gl_reconciliation.extract_match: %s", summary)
    return {"matches": matches, "discrepancies": disc_dicts,
            "human_review_required": len(discs) > 0,
            "result": {"matches": matches, "discrepancies": disc_dicts,
                       "by_type": by_type, "total_impact": total_impact, "summary": summary}}

def flag_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    discs = state.get("discrepancies") or []
    prior = state.get("token_usage") or []
    if not discs:
        return {**usage_update(None, prior)}
    user = (f"Review {len(discs)} GL discrepancies and provide remediation.\n\n"
            f"{json.dumps(discs[:20], default=str)}\n\n"
            f"Return JSON: {{\"assessments\": [{{\"discrepancy_type\": ..., \"gl_entry_id\": ..., \"resolution\": ..., \"priority\": ...}}]}}")
    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(
            invoke_llm([{"role": "user", "content": user}], task_type="reasoning",
                       system=GL_RECONCILIATION_SYSTEM, tenant_id=state.get("tenant_id")))
    except Exception:
        try:
            content, usage = invoke_claude([{"role": "user", "content": user}], system=GL_RECONCILIATION_SYSTEM)
        except Exception as e:
            return {"error": str(e), **usage_update(None, prior)}
    text = content.strip()
    for pat in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m: text = m.group(1).strip(); break
    try: out = json.loads(text)
    except json.JSONDecodeError: out = {"assessments": []}
    return {"recommended_actions": out.get("assessments", []), **usage_update(usage, prior)}

def report_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    result = state.get("result") or {}
    return {"human_review_required": True,
            "result": {**result, "recommended_actions": state.get("recommended_actions", []), "awaiting_review": True}}

def get_graph():
    graph = StateGraph(GLReconciliationState)
    graph.add_node("extract_match", extract_match_node)
    graph.add_node("flag", flag_node)
    graph.add_node("report", report_node)
    graph.set_entry_point("extract_match")
    graph.add_conditional_edges("extract_match",
        lambda s: "flag" if as_dict(s).get("human_review_required") else "__end__",
        ["flag", "__end__"])
    graph.add_edge("flag", "report")
    graph.add_edge("report", END)
    return graph.compile()
