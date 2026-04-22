"""Per-tenant configuration for the VMS Reconciliation agent.

Configurable thresholds for reconciliation matching confidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentSetting

AGENT_TYPE = "vms_reconciliation"


@dataclass(frozen=True)
class VMSReconciliationConfig:
    """Thresholds for VMS-to-ATS reconciliation."""

    auto_approve_confidence: float = 0.90
    review_confidence: float = 0.60
    hours_tolerance_pct: float = 5.0
    rate_tolerance_pct: float = 5.0
    max_records_per_batch: int = 50


def _apply_override(cfg: VMSReconciliationConfig, key: str, value: Any) -> VMSReconciliationConfig:
    """Return a new config with a single override applied."""
    fields = {
        "auto_approve_confidence": (float, 0.5, 1.0),
        "review_confidence": (float, 0.3, 1.0),
        "hours_tolerance_pct": (float, 0.0, 25.0),
        "rate_tolerance_pct": (float, 0.0, 25.0),
        "max_records_per_batch": (int, 10, 200),
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
        "auto_approve_confidence": cfg.auto_approve_confidence,
        "review_confidence": cfg.review_confidence,
        "hours_tolerance_pct": cfg.hours_tolerance_pct,
        "rate_tolerance_pct": cfg.rate_tolerance_pct,
        "max_records_per_batch": cfg.max_records_per_batch,
    }
    kwargs[key] = v
    return VMSReconciliationConfig(**kwargs)


async def load_config(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> VMSReconciliationConfig:
    """Return merged config for this tenant."""
    platform = VMSReconciliationConfig()
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
