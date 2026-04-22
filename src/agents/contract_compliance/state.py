"""State for the Contract Compliance agent."""
from __future__ import annotations
from typing import Any
from src.shared.state import AgentState

class ContractComplianceState(AgentState):
    placements: list[dict[str, Any]] = []
    contracts: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
