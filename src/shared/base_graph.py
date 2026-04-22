"""
Base utilities for building LangGraph agent graphs.
Each agent defines its own graph with analyze -> (optional HITL) -> result.
"""
from typing import Any, Callable, Optional

from langgraph.graph import END, StateGraph

from src.shared.state import AgentState


def add_hitl_conditional(
    graph: StateGraph,
    after_node: str,
    *,
    route_to_hitl: str = "human_review",
    end_node: str = END,
) -> None:
    """
    Add conditional edge: after_node -> human_review if human_review_required else END.
    Assumes graph has node `route_to_hitl` and that node has edge to END.
    """
    def router(state: dict[str, Any]) -> str:
        if state.get("human_review_required"):
            return route_to_hitl
        return end_node

    graph.add_conditional_edges(after_node, router, [route_to_hitl, end_node])


def create_agent_graph(
    name: str,
    state_schema: type[AgentState],
    entry_node: str,
    nodes: dict[str, Callable],
    edges: Optional[list[tuple[str, str]]] = None,
    entry_point: Optional[str] = None,
) -> Any:
    """
    Create a compiled StateGraph for an agent.
    - entry_point defaults to entry_node
    - edges: list of (from, to); if None, only entry -> entry_node is set.
    """
    graph = StateGraph(state_schema)
    for node_name, fn in nodes.items():
        graph.add_node(node_name, fn)
    graph.set_entry_point(entry_point or entry_node)
    graph.add_edge(entry_point or entry_node, entry_node)
    if edges:
        for a, b in edges:
            graph.add_edge(a, b)
    return graph.compile()
