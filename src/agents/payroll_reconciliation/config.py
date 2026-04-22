"""Per-tenant configuration for the Payroll Reconciliation agent."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app_platform.api.models import AgentSetting

AGENT_TYPE = "payroll_reconciliation"

@dataclass(frozen=True)
class PayrollReconciliationConfig:
    amount_tolerance_pct: float = 0.5
    auto_approve_confidence: float = 0.98
    tax_withholding_tolerance: float = 0.05
    max_days_gap: int = 14

_FIELDS = {
    "amount_tolerance_pct": (float, 0.0, 10.0),
    "auto_approve_confidence": (float, 0.5, 1.0),
    "tax_withholding_tolerance": (float, 0.0, 1.0),
    "max_days_gap": (int, 1, 60),
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
    return PayrollReconciliationConfig(**kwargs)

async def load_config(session: AsyncSession, *, tenant_id: UUID) -> PayrollReconciliationConfig:
    platform = PayrollReconciliationConfig()
    rows = (await session.execute(select(AgentSetting).where(
        and_(AgentSetting.tenant_id == tenant_id, AgentSetting.agent_type == AGENT_TYPE)
    ))).scalars().all()
    merged = platform
    for row in rows:
        merged = _apply_override(merged, row.setting_key, row.setting_value)
    return merged
