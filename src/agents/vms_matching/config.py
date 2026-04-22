"""Per-tenant configuration for the VMS Matching agent.

Follows the same pattern as ``time_anomaly/config.py``: platform
defaults as frozen dataclasses, tenant overrides merged from
``agent_settings``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentSetting

AGENT_TYPE = "vms_matching"


@dataclass(frozen=True)
class VMSMatchingConfig:
    """Thresholds for VMS name matching confidence tiers."""

    auto_accept_threshold: float = 0.95
    needs_review_threshold: float = 0.70
    fuzzy_match_min_score: float = 0.85
    rate_variance_tolerance_pct: float = 5.0
    date_range_tolerance_days: int = 30


def _apply_override(cfg: VMSMatchingConfig, key: str, value: Any) -> VMSMatchingConfig:
    """Return a new config with a single override applied."""
    try:
        if key == "auto_accept_threshold":
            v = float(value)
            if not (0.5 <= v <= 1.0):
                return cfg
            return VMSMatchingConfig(
                auto_accept_threshold=v,
                needs_review_threshold=cfg.needs_review_threshold,
                fuzzy_match_min_score=cfg.fuzzy_match_min_score,
                rate_variance_tolerance_pct=cfg.rate_variance_tolerance_pct,
                date_range_tolerance_days=cfg.date_range_tolerance_days,
            )
        if key == "needs_review_threshold":
            v = float(value)
            if not (0.3 <= v <= 1.0):
                return cfg
            return VMSMatchingConfig(
                auto_accept_threshold=cfg.auto_accept_threshold,
                needs_review_threshold=v,
                fuzzy_match_min_score=cfg.fuzzy_match_min_score,
                rate_variance_tolerance_pct=cfg.rate_variance_tolerance_pct,
                date_range_tolerance_days=cfg.date_range_tolerance_days,
            )
        if key == "fuzzy_match_min_score":
            v = float(value)
            if not (0.5 <= v <= 1.0):
                return cfg
            return VMSMatchingConfig(
                auto_accept_threshold=cfg.auto_accept_threshold,
                needs_review_threshold=cfg.needs_review_threshold,
                fuzzy_match_min_score=v,
                rate_variance_tolerance_pct=cfg.rate_variance_tolerance_pct,
                date_range_tolerance_days=cfg.date_range_tolerance_days,
            )
        if key == "rate_variance_tolerance_pct":
            v = float(value)
            if not (0.0 <= v <= 50.0):
                return cfg
            return VMSMatchingConfig(
                auto_accept_threshold=cfg.auto_accept_threshold,
                needs_review_threshold=cfg.needs_review_threshold,
                fuzzy_match_min_score=cfg.fuzzy_match_min_score,
                rate_variance_tolerance_pct=v,
                date_range_tolerance_days=cfg.date_range_tolerance_days,
            )
        if key == "date_range_tolerance_days":
            v = int(value)
            if not (0 <= v <= 180):
                return cfg
            return VMSMatchingConfig(
                auto_accept_threshold=cfg.auto_accept_threshold,
                needs_review_threshold=cfg.needs_review_threshold,
                fuzzy_match_min_score=cfg.fuzzy_match_min_score,
                rate_variance_tolerance_pct=cfg.rate_variance_tolerance_pct,
                date_range_tolerance_days=v,
            )
    except (TypeError, ValueError):
        pass
    return cfg


async def load_config(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> VMSMatchingConfig:
    """Return merged config for this tenant."""
    platform = VMSMatchingConfig()
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
