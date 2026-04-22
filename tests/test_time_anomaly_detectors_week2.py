"""Unit tests for Group A2, B, and C detectors.

Group A1 is covered in ``test_time_anomaly_detectors.py``; this file
focuses on the Week 2 detectors shipped in PR-D.

A programmable ``_StubSession`` returns pre-scripted responses for each
``session.execute`` call. Queries are matched by the order the detector
issues them — this is looser than matching SQL text, but it is exactly
what the detector bodies guarantee, so a refactor that reorders queries
will correctly show up as a test failure.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app_platform.api.models import ExceptionRegistry
from src.agents.time_anomaly.benchmarks import Benchmark, IBenchmarkProvider
from src.agents.time_anomaly.config import (
    GroupBConfig,
    GroupCConfig,
    TimeAnomalyConfig,
)
from src.agents.time_anomaly.detectors import (
    AlertCandidate,
    DetectContext,
    detect_group_a2,
    detect_group_b,
    detect_group_c,
)


TENANT = uuid.uuid4()
PLACEMENT = uuid.uuid4()
BH_PLACEMENT = "BH-777"


def _ctx(
    *,
    has_timesheet: bool,
    timesheet_overrides: dict[str, Any] | None = None,
) -> DetectContext:
    ts: dict[str, Any] | None = None
    if has_timesheet:
        ts = {"id": "TS-1", "regular_hours": 40, "overtime_hours": 0, "total_hours": 40}
        if timesheet_overrides:
            ts.update(timesheet_overrides)
    return DetectContext(
        tenant_id=TENANT,
        placement_id=PLACEMENT,
        candidate_id=None,
        pay_period_start=date(2026, 4, 20),
        pay_period_end=date(2026, 4, 26),
        bullhorn_placement_id=BH_PLACEMENT,
        current_timesheet=ts,
    )


# ── session plumbing (shared) ────────────────────────────────────────


class _FirstReturnsResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def first(self) -> Any:
        return self._value


class _ScalarsResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def first(self) -> Any:
        return self._value

    def all(self) -> list[Any]:
        if self._value is None:
            return []
        if isinstance(self._value, list):
            return list(self._value)
        return [self._value]


class _AllReturnsResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._rows[0] if self._rows else None)


class _CompositeResult:
    """Result object supporting both ``.first()``, ``.all()`` and
    ``.scalars().first()`` so the same stub works across the detector
    query shapes."""

    def __init__(
        self,
        *,
        first: Any = None,
        all_rows: list[Any] | None = None,
        scalars_first: Any = None,
    ) -> None:
        self._first = first
        self._all = all_rows or []
        self._scalars_first = scalars_first

    def first(self) -> Any:
        return self._first

    def all(self) -> list[Any]:
        return list(self._all)

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._scalars_first)


class _Stub:
    """Async session stub with a scripted queue of results."""

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.calls: int = 0

    async def execute(self, _stmt: Any) -> Any:
        self.calls += 1
        if not self._results:
            raise AssertionError(
                f"detector issued query #{self.calls} but stub was "
                "programmed with fewer results"
            )
        return self._results.pop(0)


# ── Group A2 ─────────────────────────────────────────────────────────


@dataclass
class _PriorMissRow:
    pay_period_end: date
    resolution: str | None


def test_a2_quiet_path_when_timesheet_exists() -> None:
    """A2 should short-circuit without touching the DB when a timesheet
    for this cycle already exists."""

    import asyncio

    class _Trap:
        async def execute(self, *_: Any, **__: Any) -> Any:
            raise AssertionError("A2 must not query DB when timesheet is present")

    result = asyncio.run(
        detect_group_a2(
            _Trap(),  # type: ignore[arg-type]
            ctx=_ctx(has_timesheet=True),
            cfg=TimeAnomalyConfig(),
        )
    )
    assert result is None


@pytest.mark.asyncio
async def test_a2_fires_when_threshold_consecutive_misses() -> None:
    stub = _Stub(
        [
            _CompositeResult(scalars_first=None),  # suppression lookup (scalars().first())
            _CompositeResult(first=None),  # open-alert lookup
            _AllReturnsResult(
                [  # prior misses, most recent first
                    _PriorMissRow(date(2026, 4, 19), resolution=None),
                ]
            ),
        ]
    )
    cfg = TimeAnomalyConfig()  # threshold defaults to 2
    result = await detect_group_a2(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=False),
        cfg=cfg,
    )
    assert isinstance(result, AlertCandidate)
    assert result.alert_type == "group_a2_consecutive_miss"
    assert result.severity == "high"
    assert result.trigger_context["consecutive_cycles_missed"] == 2


@pytest.mark.asyncio
async def test_a2_quiet_when_prior_cycle_resolved_as_corrected() -> None:
    """If the most recent prior miss was later corrected by the
    employee, the streak breaks and A2 should not fire."""
    stub = _Stub(
        [
            _CompositeResult(scalars_first=None),
            _CompositeResult(first=None),
            _AllReturnsResult(
                [_PriorMissRow(date(2026, 4, 19), resolution="employee_corrected")]
            ),
        ]
    )
    result = await detect_group_a2(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=False),
        cfg=TimeAnomalyConfig(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_a2_suppressed_by_exception_registry() -> None:
    stub = _Stub(
        [
            _CompositeResult(scalars_first=ExceptionRegistry(tenant_id=TENANT)),
        ]
    )
    result = await detect_group_a2(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=False),
        cfg=TimeAnomalyConfig(),
    )
    assert result is None


# ── Group B ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_b_reg_over_limit_fires() -> None:
    stub = _Stub(
        [
            _CompositeResult(first=None),  # open-alert lookup
            _CompositeResult(scalars_first=None),  # suppression lookup
        ]
    )
    cfg = TimeAnomalyConfig()
    result = await detect_group_b(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 48,
                "overtime_hours": 0,
                "total_hours": 48,
            },
        ),
        cfg=cfg,
    )
    assert isinstance(result, AlertCandidate)
    assert result.alert_type == "group_b_reg_over_limit"
    assert result.trigger_context["observed_hours"] == 48
    assert result.trigger_context["limit_hours"] == pytest.approx(40)


@pytest.mark.asyncio
async def test_b_prefers_total_over_ot_over_reg() -> None:
    """When reg+ot+total all exceed their limits, only the most severe
    variant (total) should fire."""
    stub = _Stub(
        [
            _CompositeResult(first=None),
            _CompositeResult(scalars_first=None),
        ]
    )
    cfg = TimeAnomalyConfig(
        group_b=GroupBConfig(
            reg_hours_limit=40, ot_hours_limit=20, total_hours_limit=60
        )
    )
    result = await detect_group_b(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 45,
                "overtime_hours": 25,
                "total_hours": 70,
            },
        ),
        cfg=cfg,
    )
    assert result is not None
    assert result.alert_type == "group_b_total_over_limit"


@pytest.mark.asyncio
async def test_b_quiet_when_under_all_limits() -> None:
    stub = _Stub(
        [
            _CompositeResult(first=None),
        ]
    )
    result = await detect_group_b(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 40,
                "overtime_hours": 5,
                "total_hours": 45,
            },
        ),
        cfg=TimeAnomalyConfig(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_b_suppressed_by_exception_registry() -> None:
    stub = _Stub(
        [
            _CompositeResult(first=None),
            _CompositeResult(scalars_first=ExceptionRegistry(tenant_id=TENANT)),
        ]
    )
    result = await detect_group_b(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 50,
                "overtime_hours": 0,
                "total_hours": 50,
            },
        ),
        cfg=TimeAnomalyConfig(),
    )
    assert result is None


# ── Group C ──────────────────────────────────────────────────────────


class _FixedBenchmarkProvider:
    """Deterministic IBenchmarkProvider for tests."""

    def __init__(self, benchmark: Benchmark | None) -> None:
        self._b = benchmark

    async def get_benchmark(
        self,
        session: Any,
        *,
        tenant_id: uuid.UUID,
        placement_id: uuid.UUID,
        candidate_id: uuid.UUID | None,
        pay_period_end: date,
    ) -> Benchmark | None:
        return self._b


def _benchmark(total: float, sample: int = 6) -> Benchmark:
    return Benchmark(
        expected_regular_hours=total,
        expected_overtime_hours=0,
        expected_total_hours=total,
        sample_size=sample,
        basis="employee_history",
        provider="HistoricalAverageProvider",
    )


@pytest.mark.asyncio
async def test_c_fires_when_variance_exceeds_tolerance() -> None:
    stub = _Stub(
        [
            _CompositeResult(first=None),  # open-alert lookup
            _CompositeResult(scalars_first=None),  # suppression lookup
        ]
    )
    provider: IBenchmarkProvider = _FixedBenchmarkProvider(_benchmark(40))
    cfg = TimeAnomalyConfig(group_c=GroupCConfig(tolerance_pct=0.25))
    result = await detect_group_c(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 60,
                "overtime_hours": 0,
                "total_hours": 60,  # 50% over baseline of 40
            },
        ),
        cfg=cfg,
        benchmark_provider=provider,
    )
    assert result is not None
    assert result.alert_type == "group_c_variance"
    assert result.trigger_context["variance_ratio"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_c_quiet_when_within_tolerance() -> None:
    stub = _Stub([_CompositeResult(first=None)])
    provider: IBenchmarkProvider = _FixedBenchmarkProvider(_benchmark(40))
    cfg = TimeAnomalyConfig(group_c=GroupCConfig(tolerance_pct=0.25))
    result = await detect_group_c(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 45,
                "overtime_hours": 0,
                "total_hours": 45,  # 12.5% variance, within tolerance
            },
        ),
        cfg=cfg,
        benchmark_provider=provider,
    )
    assert result is None


@pytest.mark.asyncio
async def test_c_suppressed_by_hard_mute() -> None:
    """A suppression row with magnitude_threshold=NULL is a hard mute."""
    suppression = ExceptionRegistry(
        tenant_id=TENANT,
        magnitude_threshold=None,
    )
    stub = _Stub(
        [
            _CompositeResult(first=None),
            _CompositeResult(scalars_first=suppression),
        ]
    )
    provider: IBenchmarkProvider = _FixedBenchmarkProvider(_benchmark(40))
    cfg = TimeAnomalyConfig(group_c=GroupCConfig(tolerance_pct=0.25))
    result = await detect_group_c(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 80,
                "overtime_hours": 0,
                "total_hours": 80,
            },
        ),
        cfg=cfg,
        benchmark_provider=provider,
    )
    assert result is None


@pytest.mark.asyncio
async def test_c_magnitude_refire_when_variance_grew() -> None:
    """Previously dismissed at 0.3 magnitude; new variance is 0.7 and
    multiplier is 2.0 → new >= 0.6 threshold → re-fire."""
    suppression = ExceptionRegistry(
        tenant_id=TENANT,
        magnitude_threshold=Decimal("0.3"),
    )
    stub = _Stub(
        [
            _CompositeResult(first=None),
            _CompositeResult(scalars_first=suppression),
        ]
    )
    provider: IBenchmarkProvider = _FixedBenchmarkProvider(_benchmark(40))
    cfg = TimeAnomalyConfig(
        group_c=GroupCConfig(tolerance_pct=0.25, magnitude_multiplier=2.0)
    )
    result = await detect_group_c(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 68,
                "overtime_hours": 0,
                "total_hours": 68,  # 70% variance vs 40 baseline
            },
        ),
        cfg=cfg,
        benchmark_provider=provider,
    )
    assert result is not None
    assert result.alert_type == "group_c_variance"


@pytest.mark.asyncio
async def test_c_magnitude_suppressed_when_new_variance_similar() -> None:
    """Previously dismissed at 0.3; new variance is 0.35 and multiplier
    is 2.0 → new < 0.6 threshold → stay suppressed."""
    suppression = ExceptionRegistry(
        tenant_id=TENANT,
        magnitude_threshold=Decimal("0.3"),
    )
    stub = _Stub(
        [
            _CompositeResult(first=None),
            _CompositeResult(scalars_first=suppression),
        ]
    )
    provider: IBenchmarkProvider = _FixedBenchmarkProvider(_benchmark(40))
    cfg = TimeAnomalyConfig(
        group_c=GroupCConfig(tolerance_pct=0.25, magnitude_multiplier=2.0)
    )
    result = await detect_group_c(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(
            has_timesheet=True,
            timesheet_overrides={
                "regular_hours": 54,
                "overtime_hours": 0,
                "total_hours": 54,  # 35% variance
            },
        ),
        cfg=cfg,
        benchmark_provider=provider,
    )
    assert result is None


@pytest.mark.asyncio
async def test_c_skips_when_benchmark_empty() -> None:
    """When the benchmark provider returns None (not enough history),
    Group C should not fire rather than comparing against zero."""
    stub = _Stub([_CompositeResult(first=None)])
    provider: IBenchmarkProvider = _FixedBenchmarkProvider(None)
    result = await detect_group_c(
        stub,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=True),
        cfg=TimeAnomalyConfig(),
        benchmark_provider=provider,
    )
    assert result is None
