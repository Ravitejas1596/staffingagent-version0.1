"""Unit tests for src/agents/time_anomaly/detectors.py.

Focus: Group A1 (first-miss missing timesheet) since that's the detector
that ships end-to-end in PR-C. Coverage:

- Quiet path when a timesheet already exists.
- Alert fires when no timesheet exists and no prior-miss / suppression.
- Suppression in exception_registry mutes the alert.
- Open alert already exists → no re-fire.
- Prior-cycle miss → Group A2 territory, A1 defers.
- The stub detectors (A2/B/C) return None in v1 so the node router
  stays well-behaved.

DB access is mocked with a programmable FakeSession that returns whatever
first() / scalars().all() value the test wires up.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from src.agents.time_anomaly.benchmarks import Benchmark, IBenchmarkProvider
from src.agents.time_anomaly.config import TimeAnomalyConfig
from src.agents.time_anomaly.detectors import (
    AlertCandidate,
    DetectContext,
    detect_group_a1,
    detect_group_a2,
    detect_group_b,
    detect_group_c,
)


TENANT = uuid.uuid4()
PLACEMENT = uuid.uuid4()
BH_PLACEMENT = "BH-PLACEMENT-001"


def _ctx(*, has_timesheet: bool) -> DetectContext:
    return DetectContext(
        tenant_id=TENANT,
        placement_id=PLACEMENT,
        candidate_id=None,
        pay_period_start=date(2026, 4, 20),
        pay_period_end=date(2026, 4, 26),
        bullhorn_placement_id=BH_PLACEMENT,
        current_timesheet=(
            {"id": "TS-1", "status": "Open"} if has_timesheet else None
        ),
    )


class _FakeResultRow:
    """Stand-in for SQLAlchemy Result.first() row — bool truthy means
    "record exists". We don't need column access because detect_group_a1
    only checks ``is not None``."""


class _ScalarsStub:
    def __init__(self, first_value: Any) -> None:
        self._first = first_value

    def first(self) -> Any:
        return self._first


class _FakeResult:
    def __init__(self, first_return: Any = None, scalars_first: Any = None) -> None:
        self._first = first_return
        self._scalars_first = scalars_first

    def first(self) -> Any:
        return self._first

    def scalars(self) -> _ScalarsStub:
        return _ScalarsStub(self._scalars_first)


@dataclass
class _Plan:
    """Scripts a sequence of session.execute() results so the test reads
    top-to-bottom like the code path it exercises.

    The order matches ``detect_group_a1``'s implementation:
        1. suppression lookup   (uses .scalars().first())
        2. open-alert lookup    (uses .first())
        3. prior-miss lookup    (uses .first())
    """

    suppression: Any = None
    open_alert: Any = None
    prior_miss: Any = None


class _FakeSession:
    def __init__(self, plan: _Plan) -> None:
        self._queue: list[Any] = [
            _FakeResult(scalars_first=plan.suppression),
            _FakeResult(first_return=plan.open_alert),
            _FakeResult(first_return=plan.prior_miss),
        ]

    async def execute(self, _stmt: Any) -> Any:
        if not self._queue:
            raise AssertionError(
                "detect_group_a1 issued more queries than the test planned for"
            )
        return self._queue.pop(0)


def _cfg() -> TimeAnomalyConfig:
    return TimeAnomalyConfig()


@pytest.mark.asyncio
async def test_a1_quiet_path_when_timesheet_already_exists() -> None:
    """If the employee's timesheet is present, A1 must never fire and
    must NOT touch the DB (no suppression / alert / prior-miss queries)."""
    # No _FakeSession queries will run because A1 returns early; use a
    # session that raises if touched.

    class _Trap:
        async def execute(self, *_: Any, **__: Any) -> Any:
            raise AssertionError("detect_group_a1 must not query DB when timesheet exists")

    result = await detect_group_a1(
        _Trap(),  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=True),
        cfg=_cfg(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_a1_fires_when_no_timesheet_and_no_prior_context() -> None:
    session = _FakeSession(_Plan())
    result = await detect_group_a1(
        session,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=False),
        cfg=_cfg(),
    )
    assert isinstance(result, AlertCandidate)
    assert result.alert_type == "group_a1_first_miss"
    assert result.severity == "medium"
    assert result.trigger_context["reason"] == "first_miss_no_timesheet"
    assert result.trigger_context["placement_bullhorn_id"] == BH_PLACEMENT
    assert result.trigger_context["pay_period_start"] == "2026-04-20"


@pytest.mark.asyncio
async def test_a1_suppressed_by_exception_registry() -> None:
    session = _FakeSession(_Plan(suppression=_FakeResultRow()))
    result = await detect_group_a1(
        session,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=False),
        cfg=_cfg(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_a1_skipped_when_open_alert_already_exists_for_period() -> None:
    session = _FakeSession(_Plan(open_alert=_FakeResultRow()))
    result = await detect_group_a1(
        session,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=False),
        cfg=_cfg(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_a1_defers_to_a2_when_prior_miss_exists() -> None:
    session = _FakeSession(_Plan(prior_miss=_FakeResultRow()))
    result = await detect_group_a1(
        session,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=False),
        cfg=_cfg(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_a1_severity_comes_from_config() -> None:
    """Tenant overrides propagate via load_config → TimeAnomalyConfig;
    A1 must honor whatever severity the resolved config specifies."""
    from src.agents.time_anomaly.config import GroupAConfig

    cfg = TimeAnomalyConfig(group_a=GroupAConfig(first_miss_severity="high"))
    session = _FakeSession(_Plan())
    result = await detect_group_a1(
        session,  # type: ignore[arg-type]
        ctx=_ctx(has_timesheet=False),
        cfg=cfg,
    )
    assert result is not None
    assert result.severity == "high"


# ── stub detectors (A2 / B / C) — Week 2 ──────────────────────────────


class _NoopBenchmarkProvider:
    """IBenchmarkProvider stub for Group C detector argument wiring."""

    async def get_benchmark(
        self,
        session: Any,
        *,
        tenant_id: uuid.UUID,
        placement_id: uuid.UUID,
        candidate_id: uuid.UUID | None,
        pay_period_end: date,
    ) -> Benchmark | None:
        return None


@pytest.mark.asyncio
async def test_group_a2_stub_returns_none() -> None:
    assert await detect_group_a2(None, ctx=_ctx(has_timesheet=True), cfg=_cfg()) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_group_b_returns_none_when_no_timesheet() -> None:
    """Group B short-circuits before touching the session when there is
    no current timesheet to evaluate — no hours means no over-limit check."""
    assert await detect_group_b(None, ctx=_ctx(has_timesheet=False), cfg=_cfg()) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_group_c_returns_none_when_no_timesheet() -> None:
    """Group C also short-circuits without a timesheet. The benchmark
    provider is never consulted because there is nothing to compare."""
    provider: IBenchmarkProvider = _NoopBenchmarkProvider()
    assert (
        await detect_group_c(
            None,  # type: ignore[arg-type]
            ctx=_ctx(has_timesheet=False),
            cfg=_cfg(),
            benchmark_provider=provider,
        )
        is None
    )


def test_detect_context_is_immutable() -> None:
    """DetectContext is a frozen dataclass — nodes pass it around by
    value and must not be able to mutate it mid-flight."""
    ctx = _ctx(has_timesheet=False)
    with pytest.raises(Exception):  # FrozenInstanceError is a dataclasses exc
        ctx.placement_id = uuid.uuid4()  # type: ignore[misc]
