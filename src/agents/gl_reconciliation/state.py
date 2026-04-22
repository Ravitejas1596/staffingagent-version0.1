"""State for the GL Reconciliation agent."""
from __future__ import annotations
from typing import Any
from src.shared.state import AgentState

class GLReconciliationState(AgentState):
    gl_entries: list[dict[str, Any]] = []
    charges: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    discrepancies: list[dict[str, Any]] = []
    recommended_actions: list[dict[str, Any]] = []
