"""Google Gemini adapter for the Smart Router.

Used as the **cheapest** provider for structured matching tasks
(VMS name matching, VMS reconciliation) where pattern matching on
structured data doesn't require deep reasoning.

Gemini Flash pricing: ~$0.10 / 1M input tokens — 30x cheaper than Claude.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from src.shared.providers.base import LLMAdapter, TokenUsage

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiAdapter(LLMAdapter):
    """Google Generative AI (Gemini) adapter."""

    provider_name = "gemini"

    def __init__(self) -> None:
        self._key = os.environ.get("GOOGLE_AI_API_KEY", "")

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
        # Lazy import so the SDK isn't required at module load time when
        # the adapter isn't configured.
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise RuntimeError(
                "google-genai package is required for GeminiAdapter. "
                "Install with: pip install google-genai"
            ) from exc

        if not self._key:
            raise ValueError("GOOGLE_AI_API_KEY must be set")

        client = genai.Client(api_key=self._key)

        # Convert OpenAI/Anthropic-style messages to Gemini's format.
        # Gemini uses "user"/"model" roles (not "assistant").
        contents: list[genai_types.Content] = []
        for msg in messages:
            role = msg.get("role", "user")
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                genai_types.Content(
                    role=gemini_role,
                    parts=[genai_types.Part(text=msg.get("content", ""))],
                )
            )

        # Prepend system instruction if provided.
        config = genai_types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        if system:
            config.system_instruction = system

        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            raise

        content_text = response.text or ""
        # Extract token counts from usage metadata.
        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider=self.provider_name,
            model_id=model,
        )
        return content_text, usage
