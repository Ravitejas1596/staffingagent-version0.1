"""
Claude client for StaffingAgent agents. Single place for model and token handling.
Token usage is tracked for passthrough billing (actual + 30% post-implementation).

Includes a CircuitBreaker that stops retrying after N consecutive failures on the
same operation key — prevents the infinite-retry / token-waste bug observed in
production agentic systems.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import anthropic
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TokenUsage(BaseModel):
    """Token usage for billing passthrough."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# Circuit breaker — 3 consecutive failures on the same key → open (reject)
# ---------------------------------------------------------------------------

class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker has tripped for a given operation."""


class CircuitBreaker:
    """Track consecutive failures per operation key.

    Usage::

        breaker = CircuitBreaker(threshold=3)
        breaker.check("llm_call")        # raises CircuitBreakerOpen if tripped
        try:
            result = call_llm(...)
            breaker.record_success("llm_call")
        except Exception:
            breaker.record_failure("llm_call")
    """

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        self._failures: dict[str, int] = {}

    def check(self, key: str) -> None:
        """Raise CircuitBreakerOpen if threshold reached for *key*."""
        if self._failures.get(key, 0) >= self.threshold:
            raise CircuitBreakerOpen(
                f"Circuit breaker open: {self.threshold} consecutive failures on '{key}'"
            )

    def record_failure(self, key: str) -> int:
        """Increment failure count; return new count."""
        self._failures[key] = self._failures.get(key, 0) + 1
        count = self._failures[key]
        if count >= self.threshold:
            logger.error(
                "Circuit breaker TRIPPED for '%s' after %d consecutive failures — halting retries",
                key, count,
            )
        return count

    def record_success(self, key: str) -> None:
        """Reset failure count on success."""
        self._failures.pop(key, None)

    def is_open(self, key: str) -> bool:
        return self._failures.get(key, 0) >= self.threshold

    def reset(self, key: Optional[str] = None) -> None:
        if key is None:
            self._failures.clear()
        else:
            self._failures.pop(key, None)


_global_breaker = CircuitBreaker(threshold=3)


def get_circuit_breaker() -> CircuitBreaker:
    """Return the module-level circuit breaker instance."""
    return _global_breaker


# ---------------------------------------------------------------------------
# Anthropic client helpers
# ---------------------------------------------------------------------------

def get_client() -> anthropic.Anthropic:
    """Return synchronous Anthropic client."""
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not key:
        raise ValueError("ANTHROPIC_API_KEY must be set")
    return anthropic.Anthropic(api_key=key)


def get_async_client() -> anthropic.AsyncAnthropic:
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not key:
        raise ValueError("ANTHROPIC_API_KEY must be set")
    return anthropic.AsyncAnthropic(api_key=key)


DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 4096

_RETRY_MAX = 3
_RETRY_BACKOFF_BASE = 1  # seconds: 1, 2, 4


def invoke_claude(
    messages: list[dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    system: Optional[str] = None,
    breaker_key: str = "invoke_claude",
) -> tuple[str, TokenUsage]:
    """Synchronous Claude call with retry + circuit breaker.

    Returns (content, usage). Retries up to 3 times with exponential backoff
    on transient API errors. If the circuit breaker trips (3 consecutive
    failures across calls), raises CircuitBreakerOpen immediately.
    """
    breaker = get_circuit_breaker()
    breaker.check(breaker_key)

    client = get_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    last_exc: Optional[Exception] = None
    for attempt in range(1, _RETRY_MAX + 1):
        try:
            resp = client.messages.create(**kwargs)
            content = ""
            if resp.content and resp.content[0].type == "text":
                content = resp.content[0].text
            usage = TokenUsage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            )
            breaker.record_success(breaker_key)
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

    breaker.record_failure(breaker_key)
    raise last_exc or RuntimeError("invoke_claude failed after retries")


def usage_update(usage: Any, prior: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Return state update dict to merge: append token_usage for billing.

    Accepts both the local ``TokenUsage`` and ``providers.base.TokenUsage``
    so callers don't need to care which one they have.
    """
    prev = prior or []
    if usage is None:
        return {"token_usage": prev}
    entry = usage.model_dump() if hasattr(usage, "model_dump") else usage
    return {"token_usage": prev + [entry]}


# ── Smart Router integration ────────────────────────────────────────
#
# New agents should use ``invoke_llm()`` (async) or import the router
# directly.  ``invoke_claude()`` above remains for backward compat.


async def invoke_llm(
    messages: list[dict[str, Any]],
    *,
    task_type: str = "reasoning",
    system: Optional[str] = None,
    tenant_id: Optional[str] = None,
    tenant_overrides: Optional[dict[str, Any]] = None,
) -> tuple[str, Any]:
    """Async LLM call routed through the SmartRouter.

    This is the preferred entry point for new agent code.  Returns
    ``(content, token_usage)`` just like ``invoke_claude`` but routes
    through the multi-provider fallback chain.
    """
    from src.shared.router import get_router

    router = get_router()
    return await router.invoke(
        task_type,
        messages,
        system=system,
        tenant_id=tenant_id,
        tenant_overrides=tenant_overrides,
    )
