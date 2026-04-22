"""Per-tenant configuration for the GL Reconciliation agent."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app_platform.api.models import AgentSetting

AGENT_TYPE = "gl_reconciliation"

@dataclass(frozen=True)
class GLReconciliationConfig:
    amount_tolerance_pct: float = 1.0
    auto_approve_confidence: float = 0.95
    max_unmatched_entries: int = 50
    gl_account_filter: str = ""

_FIELDS = {
    "amount_tolerance_pct": (float, 0.0, 20.0),
    "auto_approve_confidence": (float, 0.5, 1.0),
    "max_unmatched_entries": (int, 1, 500),
}

def _apply_override(cfg, key, value):
    if key not in _FIELDS:
        if key == "gl_account_filter" and isinstance(value, str):
            kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
            kwargs["gl_account_filter"] = value
            return GLReconciliationConfig(**kwargs)
        return cfg
    cast_fn, lo, hi = _FIELDS[key]
    try:
        v = cast_fn(value)
        if not (lo <= v <= hi): return cfg
    except (TypeError, ValueError): return cfg
    kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
    kwargs[key] = v
    return GLReconciliationConfig(**kwargs)

async def load_config(session: AsyncSession, *, tenant_id: UUID) -> GLReconciliationConfig:
    platform = GLReconciliationConfig()
    rows = (await session.execute(select(AgentSetting).where(
        and_(AgentSetting.tenant_id == tenant_id, AgentSetting.agent_type == AGENT_TYPE)
    ))).scalars().all()
    merged = platform
    for row in rows:
        merged = _apply_override(merged, row.setting_key, row.setting_value)
    return merged
