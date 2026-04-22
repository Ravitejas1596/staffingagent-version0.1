"""Smart Model Router — multi-provider LLM orchestration with fallback.

This is the single entry point for all LLM calls in the platform.
Agents call ``router.invoke(task_type, messages, ...)`` and the router:

1. Looks up the routing rule for the task type
2. Merges per-tenant overrides from ``agent_settings`` (if tenant_id provided)
3. Tries the primary model
4. On failure (or circuit breaker open), falls through to fallback → tertiary
5. Logs provider/model/tokens for per-tenant billing passthrough

The existing ``invoke_claude()`` in ``llm.py`` becomes a thin backward-
compat wrapper around this router.
"""
from __future__ import annotations

import logging
from typing import Any

from src.shared.providers.base import LLMAdapter, TokenUsage
from src.shared.providers.anthropic_adapter import ClaudeAdapter
from src.shared.providers.gemini_adapter import GeminiAdapter
from src.shared.providers.openai_adapter import OpenAIAdapter
from src.shared.routing_config import (
    ModelProvider,
    ModelSpec,
    PLATFORM_DEFAULT_ROUTING,
    RoutingConfig,
    TaskRoute,
    TaskType,
)

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    """Raised when every provider in the fallback chain fails."""


class CircuitBreaker:
    """Track consecutive failures per provider:model key.

    Migrated from llm.py; now supports multi-provider keys.
    """

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        self._failures: dict[str, int] = {}

    def is_open(self, key: str) -> bool:
        return self._failures.get(key, 0) >= self.threshold

    def record_failure(self, key: str) -> int:
        self._failures[key] = self._failures.get(key, 0) + 1
        count = self._failures[key]
        if count >= self.threshold:
            logger.error(
                "Circuit breaker TRIPPED for '%s' after %d consecutive failures",
                key, count,
            )
        return count

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._failures.clear()
        else:
            self._failures.pop(key, None)


class SmartRouter:
    """Multi-provider LLM router with fallback chains and circuit breaking.

    Usage::

        router = SmartRouter()

        # Agent calls:
        content, usage = await router.invoke(
            "structured_matching", messages,
            system="You are the VMS Matching Agent...",
            tenant_id="ghr-uuid",  # optional: loads tenant overrides
        )
    """

    def __init__(
        self,
        config: RoutingConfig | None = None,
    ) -> None:
        self._config = config or PLATFORM_DEFAULT_ROUTING
        self._breaker = CircuitBreaker(threshold=self._config.circuit_breaker_threshold)

        # Initialize all provider adapters.  An adapter can be
        # unavailable (no API key) — the router just skips it.
        self._adapters: dict[ModelProvider, LLMAdapter] = {
            ModelProvider.ANTHROPIC: ClaudeAdapter(),
            ModelProvider.GEMINI: GeminiAdapter(),
            ModelProvider.OPENAI: OpenAIAdapter(),
        }

    def _resolve_route(
        self,
        task_type: str | TaskType,
        tenant_overrides: dict[str, Any] | None = None,
    ) -> TaskRoute:
        """Find the routing rule for a task type, applying tenant overrides."""
        if isinstance(task_type, str):
            task_type = TaskType(task_type)

        # Find the platform-default route for this task type.
        route: TaskRoute | None = None
        for r in self._config.routes:
            if r.task_type == task_type:
                route = r
                break

        if route is None:
            # Unknown task type — use the universal fallback.
            route = TaskRoute(
                task_type=task_type,
                primary=self._config.fallback_provider,
            )

        # Apply per-tenant overrides if provided.
        if tenant_overrides:
            primary_provider = tenant_overrides.get("routing.primary_provider")
            primary_model = tenant_overrides.get("routing.primary_model")
            fallback_provider = tenant_overrides.get("routing.fallback_provider")
            temperature = tenant_overrides.get("routing.temperature")

            if primary_provider and primary_model:
                route = route.model_copy(
                    update={
                        "primary": ModelSpec(
                            provider=ModelProvider(primary_provider),
                            model_id=primary_model,
                            temperature=float(temperature) if temperature else route.primary.temperature,
                        )
                    }
                )
            if fallback_provider:
                fallback_model = tenant_overrides.get(
                    "routing.fallback_model",
                    self._config.fallback_provider.model_id,
                )
                route = route.model_copy(
                    update={
                        "fallback": ModelSpec(
                            provider=ModelProvider(fallback_provider),
                            model_id=fallback_model,
                        )
                    }
                )

        return route

    async def invoke(
        self,
        task_type: str | TaskType,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tenant_id: str | None = None,
        tenant_overrides: dict[str, Any] | None = None,
    ) -> tuple[str, TokenUsage]:
        """Route an LLM call through the fallback chain.

        Args:
            task_type: Classification of the task (see ``TaskType``).
            messages: Chat messages in OpenAI/Anthropic format.
            system: Optional system prompt.
            tenant_id: For logging/billing attribution.
            tenant_overrides: Pre-loaded routing overrides from ``agent_settings``.

        Returns:
            (content_text, token_usage) from the first provider that succeeds.

        Raises:
            AllProvidersFailedError: Every provider in the chain failed.
        """
        route = self._resolve_route(task_type, tenant_overrides)

        specs: list[ModelSpec] = [
            s for s in [route.primary, route.fallback, route.tertiary]
            if s is not None
        ]

        last_exc: Exception | None = None
        for spec in specs:
            adapter = self._adapters.get(spec.provider)
            if adapter is None or not adapter.is_available():
                logger.debug(
                    "Skipping %s — adapter unavailable", spec.provider.value
                )
                continue

            breaker_key = f"{spec.provider.value}:{spec.model_id}"
            if self._breaker.is_open(breaker_key):
                logger.warning(
                    "Skipping %s — circuit breaker open", breaker_key
                )
                continue

            try:
                content, usage = await adapter.invoke(
                    messages,
                    system=system,
                    model=spec.model_id,
                    max_tokens=spec.max_tokens,
                    temperature=spec.temperature,
                )
                self._breaker.record_success(breaker_key)
                logger.info(
                    "router.invoke OK: task=%s provider=%s model=%s tokens=%d tenant=%s",
                    task_type if isinstance(task_type, str) else task_type.value,
                    spec.provider.value,
                    spec.model_id,
                    usage.total,
                    tenant_id or "platform",
                )
                return content, usage
            except Exception as exc:
                last_exc = exc
                self._breaker.record_failure(breaker_key)
                logger.warning(
                    "router.invoke FAILED: task=%s provider=%s model=%s error=%s — trying next",
                    task_type if isinstance(task_type, str) else task_type.value,
                    spec.provider.value,
                    spec.model_id,
                    exc,
                )

        raise AllProvidersFailedError(
            f"All providers failed for task_type={task_type}: {last_exc}"
        )


# ── Module-level singleton ───────────────────────────────────────────

_router: SmartRouter | None = None


def get_router() -> SmartRouter:
    """Return the module-level SmartRouter singleton.

    Lazy-initialized so adapters pick up env vars set after import time.
    """
    global _router
    if _router is None:
        _router = SmartRouter()
    return _router


def reset_router() -> None:
    """Reset the singleton (useful in tests)."""
    global _router
    _router = None
