"""Multi-provider LLM adapters for the StaffingAgent Smart Router.

Each adapter implements the ``LLMAdapter`` protocol so the router can
switch between providers transparently.  Platform-level API keys are
used; per-tenant usage is tracked via ``TokenUsage`` for billback.
"""
from src.shared.providers.base import LLMAdapter, TokenUsage

__all__ = ["LLMAdapter", "TokenUsage"]
