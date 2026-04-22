"""Time Anomaly Agent package.

``get_graph`` is re-exported lazily so importing
``src.agents.time_anomaly.config`` (or ``.detectors``, ``.benchmarks``,
etc.) doesn't transitively require ``langgraph`` at module-load time.
That matters for two paths:

- Unit tests for the pure modules (config / benchmarks / detectors) can
  run in a slim virtualenv without the full agent-runtime stack.
- Import cycles are kept narrow — ``graph.py`` depends on every node,
  so re-exporting it from the package init would spread that fan-out
  across unrelated callers.
"""
from __future__ import annotations

from typing import Any

__all__ = ["get_graph"]


def get_graph(*args: Any, **kwargs: Any) -> Any:
    from src.agents.time_anomaly.graph import get_graph as _inner

    return _inner(*args, **kwargs)
