"""Anthropic (Claude) adapter for the Smart Router.

Extracts the existing retry + circuit-breaker logic from ``llm.py``
into the unified ``LLMAdapter`` interface.  This is the premium
provider — used for reasoning-heavy tasks (collections prioritization,
compliance analysis) and as the universal fallback.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import anthropic

from src.shared.providers.base import LLMAdapter, TokenUsage

logger = logging.getLogger(__name__)

_RETRY_MAX = 3
_RETRY_BACKOFF_BASE = 1  # seconds: 1, 2, 4


class ClaudeAdapter(LLMAdapter):
    """Anthropic Claude adapter with retry and exponential backoff."""

    provider_name = "anthropic"

    def __init__(self) -> None:
        self._key = os.environ.get("ANTHROPIC_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._key)

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if not self._key:
            raise ValueError("ANTHROPIC_API_KEY must be set")
        return anthropic.AsyncAnthropic(api_key=self._key)

    async def invoke(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> tuple[str, TokenUsage]:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        last_exc: Exception | None = None
        for attempt in range(1, _RETRY_MAX + 1):
            try:
                resp = await client.messages.create(**kwargs)
                content = ""
                if resp.content and resp.content[0].type == "text":
                    content = resp.content[0].text
                usage = TokenUsage(
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    provider=self.provider_name,
                    model_id=model,
                )
                return content, usage
            except (anthropic.RateLimitError, anthropic.APIStatusError) as exc:
                last_exc = exc
                wait = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "Claude API error (attempt %d/%d): %s — retrying in %ds",
                    attempt, _RETRY_MAX, exc, wait,
                )
                if attempt < _RETRY_MAX:
                    time.sleep(wait)

        raise last_exc or RuntimeError("ClaudeAdapter.invoke failed after retries")
