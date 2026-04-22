"""State for the Commissions agent."""
from __future__ import annotations
from typing import Any
from src.shared.state import AgentState

class CommissionsState(AgentState):
    placements: list[dict[str, Any]] = []
    commissions: list[dict[str, Any]] = []
    validation_results: dict[str, Any] = {}
