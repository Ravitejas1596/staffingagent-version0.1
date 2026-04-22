"""Per-tenant configuration for the Contract Compliance agent."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app_platform.api.models import AgentSetting

AGENT_TYPE = "contract_compliance"

@dataclass(frozen=True)
class ContractComplianceConfig:
    notify_days_before_end: int = 30
    max_bill_rate_variance_pct: float = 5.0
    tenure_limit_months: int = 24

_FIELDS = {
    "notify_days_before_end": (int, 1, 180),
    "max_bill_rate_variance_pct": (float, 0.0, 50.0),
    "tenure_limit_months": (int, 1, 120),
}

def _apply_override(cfg, key, value):
    if key not in _FIELDS: return cfg
    cast_fn, lo, hi = _FIELDS[key]
    try:
        v = cast_fn(value)
        if not (lo <= v <= hi): return cfg
    except (TypeError, ValueError): return cfg
    kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
    kwargs[key] = v
    return ContractComplianceConfig(**kwargs)

async def load_config(session: AsyncSession, *, tenant_id: UUID) -> ContractComplianceConfig:
    platform = ContractComplianceConfig()
    rows = (await session.execute(select(AgentSetting).where(
        and_(AgentSetting.tenant_id == tenant_id, AgentSetting.agent_type == AGENT_TYPE)
    ))).scalars().all()
    merged = platform
    for row in rows:
        merged = _apply_override(merged, row.setting_key, row.setting_value)
    return merged
