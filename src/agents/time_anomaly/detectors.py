"""Detection rules for the Time Anomaly agent.

Each Group returns either ``None`` (no alert) or an :class:`AlertCandidate`
that the Detect node consumes. Detectors are pure functions against a
session + context — no LangGraph, no Twilio, no side effects — so they're
trivially unit-testable.

Group ownership of the (placement, pay_period) slot:

- **A1** (``group_a1_first_miss``) — no timesheet this cycle, first miss.
- **A2** (``group_a2_consecutive_miss``) — no timesheet AND at least one
  prior consecutive cycle also missed. Owns the miss path once A1 has
  fired once for the same placement.
- **B** (``group_b_{reg|ot|total}_over_limit``) — timesheet exists, hours
  exceed a static threshold. Three mutually-exclusive variants; we fire
  the most severe one (total > ot > reg) to avoid duplicate alerts for
  the same timesheet.
- **C** (``group_c_variance``) — timesheet exists, hours deviate from the
  employee's typical pattern by more than ``group_c.tolerance_pct``.
  Consults ``exception_registry`` for a suppression window, and honors
  ``magnitude_multiplier`` to re-fire when the new variance is
  meaningfully larger than the previously-dismissed magnitude.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentAlert, ExceptionRegistry
from src.agents.time_anomaly.benchmarks import IBenchmarkProvider
from src.agents.time_anomaly.config import TimeAnomalyConfig


@dataclass(frozen=True)
class DetectContext:
    """Inputs every detector needs. Assembled once by the Detect node."""

    tenant_id: UUID
    placement_id: UUID
    candidate_id: UUID | None
    pay_period_start: date
    pay_period_end: date
    bullhorn_placement_id: str
    current_timesheet: dict[str, Any] | None  # None means no timesheet exists


@dataclass(frozen=True)
class AlertCandidate:
    """A detector's proposal that an alert should fire."""

    alert_type: str
    severity: str
    trigger_context: dict[str, Any] = field(default_factory=dict)


async def _has_active_suppression(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    alert_type: str,
    entity_id: str,
    entity_type: str = "placement",
) -> ExceptionRegistry | None:
    """Return the most recent unexpired suppression row, or None.

    Group C needs the *row* (not just a boolean) so it can compare the
    stored ``original_magnitude`` against the current variance to decide
    whether to re-fire per ``magnitude_multiplier``. All other groups
    treat any row as "suppressed" and coerce to bool at the call site.
    """
    stmt = (
        select(ExceptionRegistry)
        .where(
            and_(
                ExceptionRegistry.tenant_id == tenant_id,
                ExceptionRegistry.agent_id == "time_anomaly",
                ExceptionRegistry.alert_type == alert_type,
                ExceptionRegistry.entity_type == entity_type,
                ExceptionRegistry.entity_id == entity_id,
                (
                    ExceptionRegistry.expires_at.is_(None)
                ) | (
                    ExceptionRegistry.expires_at > _now()
                ),
            )
        )
        .order_by(ExceptionRegistry.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


def _now() -> Any:
    """Indirection so tests can monkeypatch a fixed clock."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


async def _has_open_alert_for_period(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    placement_id: UUID,
    pay_period_start: date,
) -> bool:
    """Prevent re-firing an alert while a previous one is still open
    for the same placement + pay period."""
    stmt = select(AgentAlert.id).where(
        and_(
            AgentAlert.tenant_id == tenant_id,
            AgentAlert.placement_id == placement_id,
            AgentAlert.pay_period_start == pay_period_start,
            AgentAlert.state != "resolved",
        )
    ).limit(1)
    return (await session.execute(stmt)).first() is not None


# ── Group A1: first-miss missing timesheet ───────────────────────────

async def detect_group_a1(
    session: AsyncSession,
    *,
    ctx: DetectContext,
    cfg: TimeAnomalyConfig,
) -> AlertCandidate | None:
    """Fire when the pay period has ended and no timesheet exists yet,
    and this is the employee's FIRST miss (no immediate-prior-cycle
    missing-timesheet alert).

    Returning ``None`` covers three silent paths:
      - timesheet exists (quiet path, employee is compliant)
      - active suppression in exception_registry
      - an open alert already exists for this cycle (re-fire protection)
      - a prior cycle is already missing (Group A2 consecutive-miss
        owns this instead).
    """
    if ctx.current_timesheet is not None:
        return None

    suppressed = await _has_active_suppression(
        session,
        tenant_id=ctx.tenant_id,
        alert_type="group_a1_first_miss",
        entity_id=ctx.bullhorn_placement_id,
    )
    if suppressed is not None:
        return None
    if await _has_open_alert_for_period(
        session,
        tenant_id=ctx.tenant_id,
        placement_id=ctx.placement_id,
        pay_period_start=ctx.pay_period_start,
    ):
        return None

    # Check for prior-cycle miss. If present, Group A2 handles it.
    prior_miss_stmt = select(AgentAlert.id).where(
        and_(
            AgentAlert.tenant_id == ctx.tenant_id,
            AgentAlert.placement_id == ctx.placement_id,
            AgentAlert.alert_type.in_(
                ("group_a1_first_miss", "group_a2_consecutive_miss")
            ),
            AgentAlert.pay_period_end < ctx.pay_period_start,
        )
    ).order_by(AgentAlert.pay_period_end.desc()).limit(1)
    prior = (await session.execute(prior_miss_stmt)).first()
    if prior is not None:
        return None  # Consecutive-miss territory — A2 owns this.

    return AlertCandidate(
        alert_type="group_a1_first_miss",
        severity=cfg.group_a.first_miss_severity,
        trigger_context={
            "reason": "first_miss_no_timesheet",
            "pay_period_start": ctx.pay_period_start.isoformat(),
            "pay_period_end": ctx.pay_period_end.isoformat(),
            "placement_bullhorn_id": ctx.bullhorn_placement_id,
        },
    )


# ── Group A2: consecutive-miss missing timesheet ─────────────────────

async def detect_group_a2(
    session: AsyncSession,
    *,
    ctx: DetectContext,
    cfg: TimeAnomalyConfig,
) -> AlertCandidate | None:
    """Fire when no timesheet exists for this cycle AND at least
    ``cfg.group_a.consecutive_miss_threshold`` recent consecutive
    cycles are also on record as missing.

    The "consecutive" check is looser than strict week-over-week: we count
    the number of distinct missing-timesheet alerts fired for this
    placement in the ``consecutive_miss_threshold`` most-recent prior
    pay-period-end dates before the current cycle. A gap (a cycle with
    a resolved submission) resets the count.
    """
    if ctx.current_timesheet is not None:
        return None

    suppressed = await _has_active_suppression(
        session,
        tenant_id=ctx.tenant_id,
        alert_type="group_a2_consecutive_miss",
        entity_id=ctx.bullhorn_placement_id,
    )
    if suppressed is not None:
        return None
    if await _has_open_alert_for_period(
        session,
        tenant_id=ctx.tenant_id,
        placement_id=ctx.placement_id,
        pay_period_start=ctx.pay_period_start,
    ):
        return None

    threshold = max(1, cfg.group_a.consecutive_miss_threshold - 1)
    prior_miss_stmt = (
        select(AgentAlert.pay_period_end, AgentAlert.resolution)
        .where(
            and_(
                AgentAlert.tenant_id == ctx.tenant_id,
                AgentAlert.placement_id == ctx.placement_id,
                AgentAlert.alert_type.in_(
                    ("group_a1_first_miss", "group_a2_consecutive_miss")
                ),
                AgentAlert.pay_period_end < ctx.pay_period_start,
            )
        )
        .order_by(AgentAlert.pay_period_end.desc())
        .limit(threshold)
    )
    prior_rows = (await session.execute(prior_miss_stmt)).all()
    # Count only alerts that were NOT resolved as "employee_corrected"
    # (i.e. the timesheet never arrived). A resolved-by-correction prior
    # cycle breaks the streak.
    streak = 0
    for row in prior_rows:
        resolution = row.resolution
        if resolution == "employee_corrected":
            break
        streak += 1

    if streak < threshold:
        return None

    return AlertCandidate(
        alert_type="group_a2_consecutive_miss",
        severity=cfg.group_a.consecutive_miss_severity,
        trigger_context={
            "reason": "consecutive_miss_no_timesheet",
            "pay_period_start": ctx.pay_period_start.isoformat(),
            "pay_period_end": ctx.pay_period_end.isoformat(),
            "placement_bullhorn_id": ctx.bullhorn_placement_id,
            "consecutive_cycles_missed": streak + 1,  # include current
        },
    )


# ── Group B: hours over limit ────────────────────────────────────────

def _timesheet_hours(
    timesheet: dict[str, Any],
) -> tuple[float, float, float]:
    """Extract (reg_hours, ot_hours, total_hours) from a timesheet dict.

    The Bullhorn response shape isn't locked yet (TODO(josh, apr-22)),
    so we accept multiple likely key names and coerce to floats, falling
    back to 0.0 for missing values. Unit tests pin this down.
    """
    reg = _to_float(
        timesheet.get("regular_hours")
        or timesheet.get("regularHours")
        or timesheet.get("reg_hours")
        or 0
    )
    ot = _to_float(
        timesheet.get("overtime_hours")
        or timesheet.get("ot_hours")
        or timesheet.get("overtimeHours")
        or 0
    )
    total = _to_float(
        timesheet.get("total_hours") or timesheet.get("totalHours") or reg + ot
    )
    return reg, ot, total


def _to_float(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


async def detect_group_b(
    session: AsyncSession,
    *,
    ctx: DetectContext,
    cfg: TimeAnomalyConfig,
) -> AlertCandidate | None:
    """Fire if this cycle's timesheet exceeds a static hours threshold.

    Three variants, checked in descending priority so only the most
    severe breach fires per timesheet:

        total > total_hours_limit          -> group_b_total_over_limit
        ot    > ot_hours_limit             -> group_b_ot_over_limit
        reg   > reg_hours_limit            -> group_b_reg_over_limit

    REG and OT limits are W2-only per spec, but we don't have an
    employee_type flag wired through ``DetectContext`` yet (lands with
    Josh's Bullhorn field confirmation). In the meantime we rely on the
    ``_has_active_suppression`` path so a tenant can mute the alert for
    1099 placements at the exception_registry level.
    """
    if ctx.current_timesheet is None:
        return None
    if await _has_open_alert_for_period(
        session,
        tenant_id=ctx.tenant_id,
        placement_id=ctx.placement_id,
        pay_period_start=ctx.pay_period_start,
    ):
        return None

    reg, ot, total = _timesheet_hours(ctx.current_timesheet)
    variant: str | None = None
    breach_value: float = 0.0
    breach_limit: float = 0.0
    if total > cfg.group_b.total_hours_limit:
        variant = "group_b_total_over_limit"
        breach_value = total
        breach_limit = cfg.group_b.total_hours_limit
    elif ot > cfg.group_b.ot_hours_limit:
        variant = "group_b_ot_over_limit"
        breach_value = ot
        breach_limit = cfg.group_b.ot_hours_limit
    elif reg > cfg.group_b.reg_hours_limit:
        variant = "group_b_reg_over_limit"
        breach_value = reg
        breach_limit = cfg.group_b.reg_hours_limit

    if variant is None:
        return None

    if await _has_active_suppression(
        session,
        tenant_id=ctx.tenant_id,
        alert_type=variant,
        entity_id=ctx.bullhorn_placement_id,
    ) is not None:
        return None

    return AlertCandidate(
        alert_type=variant,
        severity="medium",
        trigger_context={
            "reason": "hours_over_limit",
            "variant": variant,
            "observed_hours": breach_value,
            "limit_hours": breach_limit,
            "regular_hours": reg,
            "overtime_hours": ot,
            "total_hours": total,
            "pay_period_start": ctx.pay_period_start.isoformat(),
            "pay_period_end": ctx.pay_period_end.isoformat(),
            "placement_bullhorn_id": ctx.bullhorn_placement_id,
        },
    )


# ── Group C: variance from typical ───────────────────────────────────

async def detect_group_c(
    session: AsyncSession,
    *,
    ctx: DetectContext,
    cfg: TimeAnomalyConfig,
    benchmark_provider: IBenchmarkProvider,
) -> AlertCandidate | None:
    """Fire when this cycle's total hours deviate from the placement's
    typical pattern by more than ``cfg.group_c.tolerance_pct``.

    Suppression semantics (spec §Group C):

    - An active ``exception_registry`` row with ``magnitude_threshold``
      set means the user previously dismissed at a specific magnitude.
      We re-fire only if the *new* variance magnitude is at least
      ``cfg.group_c.magnitude_multiplier`` times that stored value.
    - An active row with ``magnitude_threshold`` = NULL is a hard mute;
      no re-fire until it expires.
    """
    if ctx.current_timesheet is None:
        return None
    if await _has_open_alert_for_period(
        session,
        tenant_id=ctx.tenant_id,
        placement_id=ctx.placement_id,
        pay_period_start=ctx.pay_period_start,
    ):
        return None

    benchmark = await benchmark_provider.get_benchmark(
        session,
        tenant_id=ctx.tenant_id,
        placement_id=ctx.placement_id,
        candidate_id=ctx.candidate_id,
        pay_period_end=ctx.pay_period_end,
    )
    if benchmark is None:
        # Not enough history — skip rather than fire against an empty baseline.
        return None

    _, _, total = _timesheet_hours(ctx.current_timesheet)
    expected = benchmark.expected_total_hours
    if expected <= 0:
        return None

    variance_ratio = abs(total - expected) / expected
    if variance_ratio <= cfg.group_c.tolerance_pct:
        return None

    suppression = await _has_active_suppression(
        session,
        tenant_id=ctx.tenant_id,
        alert_type="group_c_variance",
        entity_id=ctx.bullhorn_placement_id,
    )
    if suppression is not None:
        # Hard mute (no magnitude_threshold) unconditionally suppresses.
        threshold = suppression.magnitude_threshold
        if threshold is None:
            return None
        # Magnitude-aware re-fire: only fire if the new variance is at
        # least ``magnitude_multiplier`` times the stored dismissal.
        try:
            threshold_val = float(threshold)
        except (TypeError, ValueError):
            threshold_val = 0.0
        min_refire = threshold_val * cfg.group_c.magnitude_multiplier
        if variance_ratio < min_refire:
            return None

    return AlertCandidate(
        alert_type="group_c_variance",
        severity="medium",
        trigger_context={
            "reason": "variance_from_typical",
            "observed_total_hours": total,
            "expected_total_hours": expected,
            "variance_ratio": variance_ratio,
            "tolerance_pct": cfg.group_c.tolerance_pct,
            "benchmark_sample_size": benchmark.sample_size,
            "benchmark_basis": benchmark.basis,
            "benchmark_provider": benchmark.provider,
            "pay_period_start": ctx.pay_period_start.isoformat(),
            "pay_period_end": ctx.pay_period_end.isoformat(),
            "placement_bullhorn_id": ctx.bullhorn_placement_id,
        },
    )


# Helper kept public so PR-E (HITL endpoints) can reuse the lookback
# clamp when pre-seeding exception_registry rows from a user's bulk
# "silence this placement" action.
def group_c_suppression_expiry(cfg: TimeAnomalyConfig, *, from_date: date) -> date:
    """Return the expiry date for a fresh Group C suppression."""
    return from_date + timedelta(days=cfg.group_c.suppression_window_days)
