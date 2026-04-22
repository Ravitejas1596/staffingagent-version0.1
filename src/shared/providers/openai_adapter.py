"""OpenAI adapter for the Smart Router.

Used as a mid-tier provider for structured extraction tasks
(invoice matching, PO reconciliation) where GPT-4o-mini offers
a good balance of cost and JSON extraction quality.

GPT-4o-mini pricing: ~$0.15 / 1M input tokens.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from src.shared.providers.base import LLMAdapter, TokenUsage

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIAdapter(LLMAdapter):
    """OpenAI adapter (GPT-4o-mini, GPT-4o, etc.)."""

    provider_name = "openai"

    def __init__(self) -> None:
        self._key = os.environ.get("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._key)

    async def invoke(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> tuple[str, TokenUsage]:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is required for OpenAIAdapter. "
                "Install with: pip install openai"
            ) from exc

        if not self._key:
            raise ValueError("OPENAI_API_KEY must be set")

        client = AsyncOpenAI(api_key=self._key)

        # Build messages list — OpenAI uses "system" as a role in messages.
        oai_messages: list[dict[str, str]] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for msg in messages:
            oai_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=oai_messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            logger.error("OpenAI API error: %s", exc)
            raise

        content_text = ""
        if response.choices and response.choices[0].message.content:
            content_text = response.choices[0].message.content

        input_tokens = 0
        output_tokens = 0
        if response.usage:
            input_tokens = response.usage.prompt_tokens or 0
            output_tokens = response.usage.completion_tokens or 0

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider=self.provider_name,
            model_id=model,
        )
        return content_text, usage
