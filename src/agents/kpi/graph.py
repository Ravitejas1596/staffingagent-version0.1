"""KPI Agent — 3-node LangGraph pipeline."""
from __future__ import annotations
import json, logging, re
from typing import Any
from langgraph.graph import END, StateGraph
from src.agents.kpi.analyzers import compute_agency_kpis
from src.agents.kpi.prompts import KPI_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import as_dict
from src.agents.kpi.state import KPIState
from src.agents.kpi.config import KPIConfig

logger = logging.getLogger(__name__)

def collect_metrics_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    metrics = state.get("metrics_data") or {}
    if not metrics: return {"result": {"error": "No metrics data"}, "error": "No input"}
    cfg = state.get("config_overrides") or {}
    # Use config object for analyzer
    config_obj = KPIConfig(**cfg) if cfg else KPIConfig()
    results = compute_agency_kpis(metrics, config_obj)
    return {"computed_kpis": results, "alerts": results.get("anomalies", [])}

def analyze_anomalies_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    alerts = state.get("alerts") or []
    prior = state.get("token_usage") or []
    if not alerts: return {**usage_update(None, prior)}
    
    user = (f"Analyze these KPI anomalies and provide business insights:\n\n"
            f"{json.dumps(alerts, default=str)}\n\n"
            f"Provide actionable recommendations in JSON: {{\"recommendations\": [{{\"metric\": ..., \"insight\": ..., \"action\": ...}}]}}")
    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(
            invoke_llm([{"role": "user", "content": user}], task_type="reasoning",
                       system=KPI_SYSTEM, tenant_id=state.get("tenant_id")))
    except Exception:
        try:
            content, usage = invoke_claude([{"role": "user", "content": user}], system=KPI_SYSTEM)
        except Exception as e:
            return {"error": str(e), **usage_update(None, prior)}
    text = content.strip()
    for pat in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m: text = m.group(1).strip(); break
    try: out = json.loads(text)
    except json.JSONDecodeError: out = {"recommendations": []}
    return {"recommended_actions": out.get("recommendations", []), **usage_update(usage, prior)}

def report_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    results = state.get("computed_kpis") or {}
    return {"result": {**results, "recommendations": state.get("recommended_actions", []), "summary": results.get("summary")}}

def get_graph():
    graph = StateGraph(KPIState)
    graph.add_node("collect_metrics", collect_metrics_node)
    graph.add_node("analyze_anomalies", analyze_anomalies_node)
    graph.add_node("report", report_node)
    graph.set_entry_point("collect_metrics")
    graph.add_conditional_edges("collect_metrics",
        lambda s: "analyze_anomalies" if as_dict(s).get("alerts") else "__end__",
        ["analyze_anomalies", "__end__"])
    graph.add_edge("analyze_anomalies", "report")
    graph.add_edge("report", END)
    return graph.compile()
