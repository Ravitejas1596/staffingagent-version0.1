"""Forecasting Agent — 3-node LangGraph pipeline."""
from __future__ import annotations
import json, logging, re
from typing import Any
from langgraph.graph import END, StateGraph
from src.agents.forecasting.analyzers import process_historical_trends
from src.agents.forecasting.prompts import FORECASTING_SYSTEM
from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import as_dict
from src.agents.forecasting.state import ForecastingState

logger = logging.getLogger(__name__)

def analyze_trends_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    billing = state.get("billing_history") or []
    payroll = state.get("payroll_history") or []
    if not billing: return {"result": {"error": "No billing history"}, "error": "No input"}
    analysis = process_historical_trends(billing, payroll)
    return {"trend_analysis": analysis}

def generate_forecast_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    analysis = state.get("trend_analysis") or {}
    prior = state.get("token_usage") or []
    cfg = state.get("config_overrides") or {}
    
    user = (f"Generate a financial forecast based on this trend analysis:\n\n"
            f"{json.dumps(analysis, default=str)}\n\n"
            f"Config: {json.dumps(cfg)}\n\n"
            f"Provide a 12-week forecast including best, worst, and expected scenarios in JSON.")
    try:
        import asyncio
        content, usage = asyncio.get_event_loop().run_until_complete(
            invoke_llm([{"role": "user", "content": user}], task_type="reasoning",
                       system=FORECASTING_SYSTEM, tenant_id=state.get("tenant_id")))
    except Exception:
        try:
            content, usage = invoke_claude([{"role": "user", "content": user}], system=FORECASTING_SYSTEM)
        except Exception as e:
            return {"error": str(e), **usage_update(None, prior)}
    text = content.strip()
    for pat in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m: text = m.group(1).strip(); break
    try: out = json.loads(text)
    except json.JSONDecodeError: out = {"forecast": {}}
    return {"forecast": out, **usage_update(usage, prior)}

def present_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    forecast = state.get("forecast") or {}
    analysis = state.get("trend_analysis") or {}
    return {"result": {"forecast": forecast, "trend_analysis": analysis, "summary": "Forecast generated successfully."}}

def get_graph():
    graph = StateGraph(ForecastingState)
    graph.add_node("analyze_trends", analyze_trends_node)
    graph.add_node("generate_forecast", generate_forecast_node)
    graph.add_node("present", present_node)
    graph.set_entry_point("analyze_trends")
    graph.add_edge("analyze_trends", "generate_forecast")
    graph.add_edge("generate_forecast", "present")
    graph.add_edge("present", END)
    return graph.compile()
