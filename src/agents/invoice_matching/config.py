"""Per-tenant configuration for the Invoice Matching agent.

Configurable thresholds for amount tolerance and matching confidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentSetting

AGENT_TYPE = "invoice_matching"


@dataclass(frozen=True)
class InvoiceMatchingConfig:
    """Thresholds for invoice-to-PO matching."""

    amount_tolerance_pct: float = 2.0
    auto_approve_confidence: float = 0.95
    review_confidence: float = 0.70
    max_days_between_invoice_and_po: int = 90


def _apply_override(cfg: InvoiceMatchingConfig, key: str, value: Any) -> InvoiceMatchingConfig:
    """Return a new config with a single override applied."""
    fields = {
        "amount_tolerance_pct": (float, 0.0, 20.0),
        "auto_approve_confidence": (float, 0.5, 1.0),
        "review_confidence": (float, 0.3, 1.0),
        "max_days_between_invoice_and_po": (int, 30, 365),
    }
    if key not in fields:
        return cfg
    cast_fn, lo, hi = fields[key]
    try:
        v = cast_fn(value)
        if not (lo <= v <= hi):
            return cfg
    except (TypeError, ValueError):
        return cfg

    kwargs = {
        "amount_tolerance_pct": cfg.amount_tolerance_pct,
        "auto_approve_confidence": cfg.auto_approve_confidence,
        "review_confidence": cfg.review_confidence,
        "max_days_between_invoice_and_po": cfg.max_days_between_invoice_and_po,
    }
    kwargs[key] = v
    return InvoiceMatchingConfig(**kwargs)


async def load_config(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> InvoiceMatchingConfig:
    """Return merged config for this tenant."""
    platform = InvoiceMatchingConfig()
    rows = (
        await session.execute(
            select(AgentSetting).where(
                and_(
                    AgentSetting.tenant_id == tenant_id,
                    AgentSetting.agent_type == AGENT_TYPE,
                )
            )
        )
    ).scalars().all()
    merged = platform
    for row in rows:
        merged = _apply_override(merged, row.setting_key, row.setting_value)
    return merged
