"""Per-tenant configuration for the KPI agent."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app_platform.api.models import AgentSetting

AGENT_TYPE = "kpi"

@dataclass(frozen=True)
class KPIConfig:
    target_fill_rate_pct: float = 85.0
    target_margin_pct: float = 25.0
    max_dso_days: int = 45
    kpi_thresholds: dict[str, Any] = field(default_factory=lambda: {
        "fill_rate": {"low": 70, "high": 95},
        "margin": {"low": 15, "high": 35},
        "dso": {"low": 30, "high": 60}
    })

_FIELDS = {
    "target_fill_rate_pct": (float, 0.0, 100.0),
    "target_margin_pct": (float, 0.0, 100.0),
    "max_dso_days": (int, 1, 180),
}

def _apply_override(cfg, key, value):
    if key not in _FIELDS:
        if key == "kpi_thresholds" and isinstance(value, dict):
            kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
            kwargs["kpi_thresholds"] = value
            return KPIConfig(**kwargs)
        return cfg
    cast_fn, lo, hi = _FIELDS[key]
    try:
        v = cast_fn(value)
        if not (lo <= v <= hi): return cfg
    except (TypeError, ValueError): return cfg
    kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
    kwargs[key] = v
    return KPIConfig(**kwargs)

async def load_config(session: AsyncSession, *, tenant_id: UUID) -> KPIConfig:
    platform = KPIConfig()
    rows = (await session.execute(select(AgentSetting).where(
        and_(AgentSetting.tenant_id == tenant_id, AgentSetting.agent_type == AGENT_TYPE)
    ))).scalars().all()
    merged = platform
    for row in rows:
        merged = _apply_override(merged, row.setting_key, row.setting_value)
    return merged
