"""State for the Forecasting agent."""
from __future__ import annotations
from typing import Any
from src.shared.state import AgentState

class ForecastingState(AgentState):
    billing_history: list[dict[str, Any]] = []
    payroll_history: list[dict[str, Any]] = []
    trend_analysis: dict[str, Any] = {}
    forecast: dict[str, Any] = {}
