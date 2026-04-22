"""Contract Compliance Agent — 3-node LangGraph pipeline."""
from __future__ import annotations
import json, logging, re
from typing import Any
from langgraph.graph import END, StateGraph
from src.agents.contract_compliance.detectors import detect_contract_violations, ContractViolation
from src.agents.contract_compliance.prompts import CONTRACT_COMPLIANCE_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import as_dict
from src.agents.contract_compliance.state import ContractComplianceState
from src.agents.contract_compliance.config import ContractComplianceConfig

logger = logging.getLogger(__name__)

def _violation_to_dict(v: ContractViolation) -> dict[str, Any]:
    return {"violation_type": v.violation_type, "severity": v.severity,
            "description": v.description, "placement_id": v.placement_id,
            "candidate_name": v.candidate_name, "details": v.details}

def scan_contracts_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    placements = state.get("placements") or []
    contracts = state.get("contracts") or []
    if not placements: return {"result": {"error": "No placements data"}, "error": "No input"}
    cfg = state.get("config_overrides") or {}
    config_obj = ContractComplianceConfig(**cfg) if cfg else ContractComplianceConfig()
    violations = detect_contract_violations(placements, contracts, config_obj)
    violation_dicts = [_violation_to_dict(v) for v in violations]
    return {"violations": violation_dicts, "human_review_required": len(violations) > 0}

def analyze_violations_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    violations = state.get("violations") or []
    prior = state.get("token_usage") or []
    if not violations: return {**usage_update(None, prior)}
    
    user = (f"Analyze these contract compliance violations and suggest remediation:\n\n"
            f"{json.dumps(violations[:20], default=str)}\n\n"
            f"Provide assessments in JSON: {{\"assessments\": [{{\"placement_id\": ..., \"insight\": ..., \"action\": ...}}]}}")
    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(
            invoke_llm([{"role": "user", "content": user}], task_type="reasoning",
                       system=CONTRACT_COMPLIANCE_SYSTEM, tenant_id=state.get("tenant_id")))
    except Exception:
        try:
            content, usage = invoke_claude([{"role": "user", "content": user}], system=CONTRACT_COMPLIANCE_SYSTEM)
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
    violations = state.get("violations") or []
    return {"result": {"violations": violations, "recommendations": state.get("recommended_actions", []), "summary": f"Detected {len(violations)} contract compliance violations."}}

def get_graph():
    graph = StateGraph(ContractComplianceState)
    graph.add_node("scan_contracts", scan_contracts_node)
    graph.add_node("analyze_violations", analyze_violations_node)
    graph.add_node("report", report_node)
    graph.set_entry_point("scan_contracts")
    graph.add_conditional_edges("scan_contracts",
        lambda s: "analyze_violations" if as_dict(s).get("violations") else "__end__",
        ["analyze_violations", "__end__"])
    graph.add_edge("analyze_violations", "report")
    graph.add_edge("report", END)
    return graph.compile()
