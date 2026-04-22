"""Per-tenant configuration for the Compliance agent.

Configurable thresholds for credential expiry warnings and violation severity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentSetting

AGENT_TYPE = "compliance"


@dataclass(frozen=True)
class ComplianceConfig:
    """Thresholds for compliance checks."""

    credential_expiry_warning_days: int = 30
    credential_expiry_critical_days: int = 7
    max_consecutive_weeks_without_review: int = 12
    overtime_weekly_threshold_hours: float = 40.0


def _apply_override(cfg: ComplianceConfig, key: str, value: Any) -> ComplianceConfig:
    """Return a new config with a single override applied."""
    fields = {
        "credential_expiry_warning_days": (int, 7, 180),
        "credential_expiry_critical_days": (int, 1, 30),
        "max_consecutive_weeks_without_review": (int, 4, 52),
        "overtime_weekly_threshold_hours": (float, 20.0, 80.0),
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
        "credential_expiry_warning_days": cfg.credential_expiry_warning_days,
        "credential_expiry_critical_days": cfg.credential_expiry_critical_days,
        "max_consecutive_weeks_without_review": cfg.max_consecutive_weeks_without_review,
        "overtime_weekly_threshold_hours": cfg.overtime_weekly_threshold_hours,
    }
    kwargs[key] = v
    return ComplianceConfig(**kwargs)


async def load_config(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> ComplianceConfig:
    """Return merged config for this tenant."""
    platform = ComplianceConfig()
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
