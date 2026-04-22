"""Platform-default configuration for the Time Anomaly agent.

Tenant overrides live in the ``agent_settings`` table (migration 051) and
win over anything here. Detect/outreach nodes read config via
:func:`load_config` which merges platform defaults with tenant overrides
in one place so the rest of the agent code never branches on "where did
this value come from."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentSetting

AGENT_TYPE = "time_anomaly"


@dataclass(frozen=True)
class SLABand:
    """First-reminder and escalation windows for an alert severity."""

    first_reminder_hours: int
    escalation_hours: int


@dataclass(frozen=True)
class GroupAConfig:
    """Group A — missing timesheet thresholds."""

    first_miss_severity: str = "medium"
    consecutive_miss_severity: str = "high"
    consecutive_miss_threshold: int = 2  # number of consecutive cycles to trigger A2


@dataclass(frozen=True)
class GroupBConfig:
    """Group B — hours-over-limit thresholds by variant."""

    reg_hours_limit: float = 40.0  # W2 only
    ot_hours_limit: float = 20.0   # W2 only
    total_hours_limit: float = 60.0  # any employee type


@dataclass(frozen=True)
class GroupCConfig:
    """Group C — variance-from-typical thresholds."""

    tolerance_pct: float = 0.25   # 25% tolerance by default
    basis: str = "employee_history"  # 'employee_history' | 'placement_history' | 'client_history'
    lookback_weeks: int = 8
    suppression_window_days: int = 60
    magnitude_multiplier: float = 2.0  # re-fire if new variance >= 2x previously-dismissed


@dataclass(frozen=True)
class TimeAnomalyConfig:
    """Resolved config for an agent invocation.

    Instantiate via :func:`load_config` — never construct directly in
    application code because that skips the tenant-override merge.
    """

    sla_bands: dict[str, SLABand] = field(
        default_factory=lambda: {
            "medium": SLABand(first_reminder_hours=4, escalation_hours=24),
            "high": SLABand(first_reminder_hours=2, escalation_hours=12),
        }
    )
    group_a: GroupAConfig = field(default_factory=GroupAConfig)
    group_b: GroupBConfig = field(default_factory=GroupBConfig)
    group_c: GroupCConfig = field(default_factory=GroupCConfig)
    dry_run: bool = False


def _apply_override(
    platform: TimeAnomalyConfig, key: str, value: Any
) -> TimeAnomalyConfig:
    """Return a new TimeAnomalyConfig with a single override applied.

    Keys use dotted paths: ``group_c.tolerance_pct``, ``sla_bands.high.escalation_hours``.
    Unknown keys are ignored with a debug log rather than raising — tenant
    admins shouldn't be able to break the agent by typo'ing a setting key.
    """
    parts = key.split(".")
    try:
        if parts == ["group_a", "consecutive_miss_threshold"]:
            return TimeAnomalyConfig(
                sla_bands=platform.sla_bands,
                group_a=GroupAConfig(
                    first_miss_severity=platform.group_a.first_miss_severity,
                    consecutive_miss_severity=platform.group_a.consecutive_miss_severity,
                    consecutive_miss_threshold=int(value),
                ),
                group_b=platform.group_b,
                group_c=platform.group_c,
                dry_run=platform.dry_run,
            )
        if parts == ["group_b", "reg_hours_limit"]:
            return TimeAnomalyConfig(
                sla_bands=platform.sla_bands,
                group_a=platform.group_a,
                group_b=GroupBConfig(
                    reg_hours_limit=float(value),
                    ot_hours_limit=platform.group_b.ot_hours_limit,
                    total_hours_limit=platform.group_b.total_hours_limit,
                ),
                group_c=platform.group_c,
                dry_run=platform.dry_run,
            )
        if parts == ["group_c", "tolerance_pct"]:
            return TimeAnomalyConfig(
                sla_bands=platform.sla_bands,
                group_a=platform.group_a,
                group_b=platform.group_b,
                group_c=GroupCConfig(
                    tolerance_pct=float(value),
                    basis=platform.group_c.basis,
                    lookback_weeks=platform.group_c.lookback_weeks,
                    suppression_window_days=platform.group_c.suppression_window_days,
                    magnitude_multiplier=platform.group_c.magnitude_multiplier,
                ),
                dry_run=platform.dry_run,
            )
        if parts == ["group_c", "basis"]:
            return TimeAnomalyConfig(
                sla_bands=platform.sla_bands,
                group_a=platform.group_a,
                group_b=platform.group_b,
                group_c=GroupCConfig(
                    tolerance_pct=platform.group_c.tolerance_pct,
                    basis=str(value),
                    lookback_weeks=platform.group_c.lookback_weeks,
                    suppression_window_days=platform.group_c.suppression_window_days,
                    magnitude_multiplier=platform.group_c.magnitude_multiplier,
                ),
                dry_run=platform.dry_run,
            )
        # Future override keys wire in here as explicit branches. Keeping
        # this routing explicit (vs. generic setattr) means each override
        # path is discoverable and its validation is obvious.
    except (TypeError, ValueError):
        # Bad override type; fall through to platform default.
        pass
    return platform


async def load_config(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    dry_run: bool = False,
) -> TimeAnomalyConfig:
    """Return a resolved ``TimeAnomalyConfig`` for *tenant_id*.

    Reads ``agent_settings`` rows keyed by this tenant and agent_type,
    applies each override onto the platform defaults, and returns the
    merged config.
    """
    platform = TimeAnomalyConfig(dry_run=dry_run)
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
