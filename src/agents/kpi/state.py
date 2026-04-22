"""State for the KPI agent."""
from __future__ import annotations
from typing import Any
from src.shared.state import AgentState

class KPIState(AgentState):
    metrics_data: dict[str, Any] = {}
    computed_kpis: dict[str, Any] = {}
    alerts: list[dict[str, Any]] = []
