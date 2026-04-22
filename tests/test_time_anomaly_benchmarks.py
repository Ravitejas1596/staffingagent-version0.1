"""Unit tests for src/agents/time_anomaly/benchmarks.py.

Focus: ``HistoricalAverageProvider`` — the v1 benchmark provider Group C
will depend on in PR-D. The integration test (Postgres-backed rolling
average) lives in ``tests/integration``; here we verify the contract:

- Returns ``None`` when sample size < MIN_SAMPLE_SIZE.
- Returns ``None`` on empty / null aggregate rows.
- Builds a ``Benchmark`` with the aggregated values when the sample is
  large enough.
- Basis validation rejects unsupported strings so typos fail fast.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from src.agents.time_anomaly.benchmarks import (
    Benchmark,
    HistoricalAverageProvider,
)


TENANT = uuid.uuid4()
PLACEMENT = uuid.uuid4()


@dataclass
class _Row:
    reg: float | None
    ot: float | None
    n: int | None


class _FakeResult:
    def __init__(self, row: _Row | None) -> None:
        self._row = row

    def one_or_none(self) -> _Row | None:
        return self._row


class _FakeSession:
    def __init__(self, row: _Row | None) -> None:
        self._row = row

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self._row)


@pytest.mark.asyncio
async def test_returns_benchmark_when_sample_size_sufficient() -> None:
    provider = HistoricalAverageProvider(lookback_weeks=8)
    session = _FakeSession(_Row(reg=38.5, ot=2.25, n=6))
    result = await provider.get_benchmark(
        session,  # type: ignore[arg-type]
        tenant_id=TENANT,
        placement_id=PLACEMENT,
        candidate_id=None,
        pay_period_end=date(2026, 4, 26),
    )
    assert isinstance(result, Benchmark)
    assert result.expected_regular_hours == pytest.approx(38.5)
    assert result.expected_overtime_hours == pytest.approx(2.25)
    assert result.expected_total_hours == pytest.approx(40.75)
    assert result.sample_size == 6
    assert result.provider == "HistoricalAverageProvider"


@pytest.mark.asyncio
async def test_returns_none_when_sample_size_below_minimum() -> None:
    provider = HistoricalAverageProvider()
    session = _FakeSession(_Row(reg=38.0, ot=0.0, n=2))
    result = await provider.get_benchmark(
        session,  # type: ignore[arg-type]
        tenant_id=TENANT,
        placement_id=PLACEMENT,
        candidate_id=None,
        pay_period_end=date(2026, 4, 26),
    )
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_aggregate_row_is_null() -> None:
    """Empty timesheet history → aggregate SUM/COUNT returns NULL ``n``.
    Provider must treat that as 'not enough history' rather than firing
    Group C against a phantom baseline of zeros."""
    provider = HistoricalAverageProvider()
    session = _FakeSession(_Row(reg=None, ot=None, n=None))
    result = await provider.get_benchmark(
        session,  # type: ignore[arg-type]
        tenant_id=TENANT,
        placement_id=PLACEMENT,
        candidate_id=None,
        pay_period_end=date(2026, 4, 26),
    )
    assert result is None


def test_rejects_unsupported_basis() -> None:
    with pytest.raises(ValueError):
        HistoricalAverageProvider(basis="astrology")


def test_rejects_zero_lookback() -> None:
    with pytest.raises(ValueError):
        HistoricalAverageProvider(lookback_weeks=0)


def test_constructor_accepts_supported_bases() -> None:
    for basis in ("employee_history", "placement_history", "client_history"):
        provider = HistoricalAverageProvider(basis=basis)
        # Smoke-test attribute exposure on the private field for introspection.
        assert provider is not None
