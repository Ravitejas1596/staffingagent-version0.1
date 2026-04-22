"""
Human-in-the-loop (HITL) node for StaffingAgent agents.
All purpose-built agents route to HITL when approval/review is required.
"""
from typing import Any

from langgraph.graph import StateGraph

from src.shared.state import AgentState, as_dict


def human_review_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Placeholder HITL node. In production this would:
    - Enqueue a task for a human (UI/queue)
    - Wait for human_decision to be injected (or resume via API)
    - Return updated state with human_decision applied.
    For local/dev we just pass through and set human_review_required.
    """
    state = as_dict(state)
    return {
        "human_review_required": True,
        "result": state.get("result"),
    }


def should_request_human(state: dict[str, Any]) -> str:
    """Router: continue to END or go to human_review."""
    s = as_dict(state)
    if s.get("human_review_required"):
        return "human_review"
    return "__end__"


def build_hitl_subgraph(state_schema: type[AgentState]):
    """
    Build a small subgraph: human_review -> END.
    Compose this into each agent graph where HITL is needed.
    """
    graph = StateGraph(state_schema)
    graph.add_node("human_review", human_review_node)
    graph.add_conditional_edges("human_review", lambda s: "__end__", ["__end__"])
    graph.set_entry_point("human_review")
    return graph.compile()


def apply_human_decision(state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """
    Apply human decision to state (e.g. after HITL UI submits).
    Override in each agent for agent-specific fields (e.g. approved_matches).
    """
    s = as_dict(state)
    return {
        **s,
        "human_decision": decision,
        "human_review_required": False,
    }
