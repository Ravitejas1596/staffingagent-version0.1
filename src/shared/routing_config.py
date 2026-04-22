"""Pydantic-validated routing configuration schemas.

These schemas define:
- Which model handles which task type (structured_matching, reasoning, etc.)
- Fallback chains (primary → secondary → tertiary)
- Per-route constraints (max tokens, temperature, timeout)
- Validation rules (reject bad values with clear errors)

Platform defaults are defined here.  Per-tenant overrides are stored
in the ``agent_settings`` table and merged at runtime by the router.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ModelProvider(str, Enum):
    """Supported LLM providers."""

    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class TaskType(str, Enum):
    """Classification of LLM tasks for routing decisions.

    - structured_matching: pattern matching on structured records (VMS names, reconciliation)
    - structured_extraction: JSON extraction from tabular data (invoices, POs)
    - reasoning: domain-specific analysis requiring judgment (compliance, collections)
    - drafting: professional writing for client-facing content (collection emails)
    - fallback_complex: safety net for tasks that cheaper models failed on
    """

    STRUCTURED_MATCHING = "structured_matching"
    STRUCTURED_EXTRACTION = "structured_extraction"
    REASONING = "reasoning"
    DRAFTING = "drafting"
    FALLBACK_COMPLEX = "fallback_complex"


class ModelSpec(BaseModel):
    """A specific model on a specific provider."""

    provider: ModelProvider
    model_id: str
    max_tokens: int = Field(default=4096, ge=256, le=32768)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class TaskRoute(BaseModel):
    """Routing rule for a single task type.

    Defines primary model + up to two fallbacks.  The router tries
    primary first; on failure (or circuit breaker open), falls through
    to secondary, then tertiary.
    """

    task_type: TaskType
    primary: ModelSpec
    fallback: Optional[ModelSpec] = None
    tertiary: Optional[ModelSpec] = None
    timeout_seconds: int = Field(default=30, ge=5, le=120)

    @field_validator("task_type", mode="before")
    @classmethod
    def coerce_task_type(cls, v: str) -> str:  # noqa: N805
        """Accept plain strings like ``'reasoning'`` and coerce to enum."""
        if isinstance(v, str) and not isinstance(v, TaskType):
            return TaskType(v)
        return v


class RoutingConfig(BaseModel):
    """Complete routing configuration — platform defaults or tenant override.

    Validation rules:
    - No duplicate task types
    - Fallback provider always set (Claude Sonnet as universal safety net)
    - Circuit breaker threshold between 1 and 10
    """

    routes: list[TaskRoute]
    fallback_provider: ModelSpec = Field(
        default_factory=lambda: ModelSpec(
            provider=ModelProvider.ANTHROPIC,
            model_id="claude-sonnet-4-20250514",
        )
    )
    circuit_breaker_threshold: int = Field(default=3, ge=1, le=10)
    retry_max: int = Field(default=3, ge=1, le=5)
    retry_backoff_base: float = Field(default=1.0, ge=0.5, le=5.0)

    @field_validator("routes")
    @classmethod
    def no_duplicate_task_types(cls, v: list[TaskRoute]) -> list[TaskRoute]:
        types = [r.task_type for r in v]
        if len(types) != len(set(types)):
            raise ValueError("Duplicate task_type in routes — each task type must appear once")
        return v


# ── Platform defaults ────────────────────────────────────────────────

# Claude Sonnet — premium, used for reasoning + universal fallback
_CLAUDE_SONNET = ModelSpec(
    provider=ModelProvider.ANTHROPIC,
    model_id="claude-sonnet-4-20250514",
)

# Gemini Flash — cheapest, for structured matching
_GEMINI_FLASH = ModelSpec(
    provider=ModelProvider.GEMINI,
    model_id="gemini-2.0-flash",
)

# GPT-4o-mini — mid-tier, for structured extraction
_GPT4O_MINI = ModelSpec(
    provider=ModelProvider.OPENAI,
    model_id="gpt-4o-mini",
)


PLATFORM_DEFAULT_ROUTING = RoutingConfig(
    routes=[
        TaskRoute(
            task_type=TaskType.STRUCTURED_MATCHING,
            primary=_GEMINI_FLASH,
            fallback=_CLAUDE_SONNET,
        ),
        TaskRoute(
            task_type=TaskType.STRUCTURED_EXTRACTION,
            primary=_GPT4O_MINI,
            fallback=_CLAUDE_SONNET,
        ),
        TaskRoute(
            task_type=TaskType.REASONING,
            primary=_CLAUDE_SONNET,
            fallback=_GPT4O_MINI,
        ),
        TaskRoute(
            task_type=TaskType.DRAFTING,
            primary=_CLAUDE_SONNET,
            fallback=_GPT4O_MINI,
        ),
        TaskRoute(
            task_type=TaskType.FALLBACK_COMPLEX,
            primary=_CLAUDE_SONNET,
        ),
    ],
    fallback_provider=_CLAUDE_SONNET,
)
