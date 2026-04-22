"""Payroll Reconciliation Agent — 3-node LangGraph pipeline."""
from __future__ import annotations
import json, logging, re
from typing import Any
from langgraph.graph import END, StateGraph
from src.agents.payroll_reconciliation.detectors import reconcile_payroll_to_charges, PayrollDiscrepancy
from src.agents.payroll_reconciliation.prompts import PAYROLL_RECONCILIATION_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import as_dict
from src.agents.payroll_reconciliation.state import PayrollReconciliationState

logger = logging.getLogger(__name__)

def _disc_to_dict(d: PayrollDiscrepancy) -> dict[str, Any]:
    return {"discrepancy_type": d.discrepancy_type, "severity": d.severity,
            "description": d.description, "payroll_id": d.payroll_id,
            "charge_id": d.charge_id, "candidate_name": d.candidate_name,
            "financial_impact": d.financial_impact, "details": d.details}

def extract_match_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    pr = state.get("payroll_records") or []
    charges = state.get("charges") or []
    if not pr and not charges:
        return {"result": {"error": "No payroll records or charges"}, "error": "No input"}
    cfg = state.get("config_overrides") or {}
    matches, discs = reconcile_payroll_to_charges(
        pr, charges, amount_tolerance_pct=float(cfg.get("amount_tolerance_pct", 0.5)))
    disc_dicts = [_disc_to_dict(d) for d in discs]
    total_impact = sum(abs(d.financial_impact or 0) for d in discs)
    summary = f"Reconciled {len(matches)} payroll records, found {len(discs)} discrepancies, ${total_impact:,.2f} impact"
    return {"matches": matches, "discrepancies": disc_dicts,
            "human_review_required": len(discs) > 0,
            "result": {"matches": matches, "discrepancies": disc_dicts, "total_impact": total_impact, "summary": summary}}

def analyze_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    discs = state.get("discrepancies") or []
    prior = state.get("token_usage") or []
    if not discs: return {**usage_update(None, prior)}
    user = (f"Analyze {len(discs)} payroll discrepancies.\n\n"
            f"{json.dumps(discs[:20], default=str)}\n\n"
            f"Provide resolution steps for each in JSON: {{\"assessments\": [{{\"payroll_id\": ..., \"resolution\": ..., \"priority\": ...}}]}}")
    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(
            invoke_llm([{"role": "user", "content": user}], task_type="reasoning",
                       system=PAYROLL_RECONCILIATION_SYSTEM, tenant_id=state.get("tenant_id")))
    except Exception:
        try:
            content, usage = invoke_claude([{"role": "user", "content": user}], system=PAYROLL_RECONCILIATION_SYSTEM)
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
    graph = StateGraph(PayrollReconciliationState)
    graph.add_node("extract_match", extract_match_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("report", report_node)
    graph.set_entry_point("extract_match")
    graph.add_conditional_edges("extract_match",
        lambda s: "analyze" if as_dict(s).get("human_review_required") else "__end__",
        ["analyze", "__end__"])
    graph.add_edge("analyze", "report")
    graph.add_edge("report", END)
    return graph.compile()
