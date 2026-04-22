"""Per-tenant configuration for the Collections agent.

Configurable thresholds for AR aging tiers and escalation timing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentSetting

AGENT_TYPE = "collections"


@dataclass(frozen=True)
class CollectionsConfig:
    """Thresholds for collections prioritization and escalation."""

    reminder_days: int = 15
    followup_days: int = 30
    escalation_days: int = 60
    legal_escalation_days: int = 90
    high_priority_amount: float = 10000.0
    critical_priority_amount: float = 50000.0


def _apply_override(cfg: CollectionsConfig, key: str, value: Any) -> CollectionsConfig:
    """Return a new config with a single override applied."""
    fields = {
        "reminder_days": (int, 1, 90),
        "followup_days": (int, 7, 120),
        "escalation_days": (int, 14, 180),
        "legal_escalation_days": (int, 30, 365),
        "high_priority_amount": (float, 1000.0, 500000.0),
        "critical_priority_amount": (float, 5000.0, 1000000.0),
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
        "reminder_days": cfg.reminder_days,
        "followup_days": cfg.followup_days,
        "escalation_days": cfg.escalation_days,
        "legal_escalation_days": cfg.legal_escalation_days,
        "high_priority_amount": cfg.high_priority_amount,
        "critical_priority_amount": cfg.critical_priority_amount,
    }
    kwargs[key] = v
    return CollectionsConfig(**kwargs)


async def load_config(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> CollectionsConfig:
    """Return merged config for this tenant."""
    platform = CollectionsConfig()
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
