"""Per-tenant configuration for the Forecasting agent."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app_platform.api.models import AgentSetting

AGENT_TYPE = "forecasting"

@dataclass(frozen=True)
class ForecastingConfig:
    lookback_months: int = 12
    forecast_horizon_weeks: int = 12
    growth_assumption_pct: float = 0.0
    seasonality_enabled: bool = True

_FIELDS = {
    "lookback_months": (int, 1, 36),
    "forecast_horizon_weeks": (int, 1, 52),
    "growth_assumption_pct": (float, -50.0, 100.0),
}

def _apply_override(cfg, key, value):
    if key not in _FIELDS:
        if key == "seasonality_enabled" and isinstance(value, bool):
            kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
            kwargs["seasonality_enabled"] = value
            return ForecastingConfig(**kwargs)
        return cfg
    cast_fn, lo, hi = _FIELDS[key]
    try:
        v = cast_fn(value)
        if not (lo <= v <= hi): return cfg
    except (TypeError, ValueError): return cfg
    kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
    kwargs[key] = v
    return ForecastingConfig(**kwargs)

async def load_config(session: AsyncSession, *, tenant_id: UUID) -> ForecastingConfig:
    platform = ForecastingConfig()
    rows = (await session.execute(select(AgentSetting).where(
        and_(AgentSetting.tenant_id == tenant_id, AgentSetting.agent_type == AGENT_TYPE)
    ))).scalars().all()
    merged = platform
    for row in rows:
        merged = _apply_override(merged, row.setting_key, row.setting_value)
    return merged
