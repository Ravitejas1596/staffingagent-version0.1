"""Per-tenant configuration for the Commissions agent."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app_platform.api.models import AgentSetting

AGENT_TYPE = "commissions"

@dataclass(frozen=True)
class CommissionsConfig:
    default_recruiter_rate_pct: float = 5.0
    default_sales_rate_pct: float = 3.0
    commission_rules: list[dict[str, Any]] = field(default_factory=lambda: [
        {"type": "recruiter", "rate": 5.0, "criteria": "percentage_of_spread"},
        {"type": "sales", "rate": 3.0, "criteria": "percentage_of_spread"}
    ])

_FIELDS = {
    "default_recruiter_rate_pct": (float, 0.0, 100.0),
    "default_sales_rate_pct": (float, 0.0, 100.0),
}

def _apply_override(cfg, key, value):
    if key not in _FIELDS:
        if key == "commission_rules" and isinstance(value, list):
            kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
            kwargs["commission_rules"] = value
            return CommissionsConfig(**kwargs)
        return cfg
    cast_fn, lo, hi = _FIELDS[key]
    try:
        v = cast_fn(value)
        if not (lo <= v <= hi): return cfg
    except (TypeError, ValueError): return cfg
    kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
    kwargs[key] = v
    return CommissionsConfig(**kwargs)

async def load_config(session: AsyncSession, *, tenant_id: UUID) -> CommissionsConfig:
    platform = CommissionsConfig()
    rows = (await session.execute(select(AgentSetting).where(
        and_(AgentSetting.tenant_id == tenant_id, AgentSetting.agent_type == AGENT_TYPE)
    ))).scalars().all()
    merged = platform
    for row in rows:
        merged = _apply_override(merged, row.setting_key, row.setting_value)
    return merged
