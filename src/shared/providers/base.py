"""Abstract base for LLM provider adapters.

Every provider (Anthropic, Google Gemini, OpenAI) implements this
interface so the ``SmartRouter`` can swap between them transparently.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class TokenUsage(BaseModel):
    """Token counts for billing passthrough (actual + 30%)."""

    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = ""
    model_id: str = ""

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMAdapter(ABC):
    """Unified interface every LLM provider must implement."""

    provider_name: str = ""

    @abstractmethod
    async def invoke(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> tuple[str, TokenUsage]:
        """Send messages and return (content_text, token_usage)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider's API key is configured."""
        ...

    def __repr__(self) -> str:
        avail = "available" if self.is_available() else "unavailable"
        return f"<{self.__class__.__name__} ({avail})>"
