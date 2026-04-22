"""Per-tenant configuration for the Risk Alert agent.

Replaces the inline literals ($7.25, $150, 0%) currently hardcoded in
``graph.py`` with configurable, validated thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentSetting

AGENT_TYPE = "risk_alert"


@dataclass(frozen=True)
class RiskAlertConfig:
    """Thresholds for all risk detection rules."""

    # Rates
    minimum_wage: float = 7.25
    high_pay_rate: float = 150.0
    high_bill_rate: float = 225.0
    state_min_wage_overrides: dict[str, float] = field(default_factory=dict)

    # Markup
    low_markup_pct: float = 10.0
    high_markup_pct: float = 250.0

    # Hours
    high_hours: float = 60.0
    bill_rate_mismatch_pct: float = 20.0

    # Amounts
    high_pay_amount: float = 5000.0
    high_bill_amount: float = 7500.0

    # Placement status classification
    approved_statuses: list[str] = field(
        default_factory=lambda: ["approved", "active", "placed"]
    )
    inactive_statuses: list[str] = field(
        default_factory=lambda: ["terminated", "cancelled", "closed", "inactive"]
    )


# Field validation rules: (cast_fn, min_val, max_val)
_FIELDS: dict[str, tuple[type, float, float]] = {
    "minimum_wage": (float, 0.0, 50.0),
    "high_pay_rate": (float, 50.0, 500.0),
    "high_bill_rate": (float, 50.0, 1000.0),
    "low_markup_pct": (float, 0.0, 100.0),
    "high_markup_pct": (float, 50.0, 500.0),
    "high_hours": (float, 20.0, 168.0),
    "bill_rate_mismatch_pct": (float, 1.0, 100.0),
    "high_pay_amount": (float, 100.0, 100000.0),
    "high_bill_amount": (float, 100.0, 100000.0),
}


def _apply_override(cfg: RiskAlertConfig, key: str, value: Any) -> RiskAlertConfig:
    """Return a new config with a single override applied."""
    # Handle dict/list fields specially
    if key == "state_min_wage_overrides" and isinstance(value, dict):
        return RiskAlertConfig(
            **{k: getattr(cfg, k) for k in cfg.__dataclass_fields__ if k != key},
            state_min_wage_overrides={
                s.upper(): float(v) for s, v in value.items()
            },
        )
    if key in ("approved_statuses", "inactive_statuses") and isinstance(value, list):
        kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__ if k != key}
        kwargs[key] = [str(v).strip() for v in value]
        return RiskAlertConfig(**kwargs)

    # Scalar fields
    if key not in _FIELDS:
        return cfg
    cast_fn, lo, hi = _FIELDS[key]
    try:
        v = cast_fn(value)
        if not (lo <= v <= hi):
            return cfg
    except (TypeError, ValueError):
        return cfg

    kwargs = {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}
    kwargs[key] = v
    return RiskAlertConfig(**kwargs)


async def load_config(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> RiskAlertConfig:
    """Return merged config for this tenant."""
    platform = RiskAlertConfig()
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
