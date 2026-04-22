"""Benchmark providers for Group C (variance-from-typical) detection.

The ``IBenchmarkProvider`` protocol is the seam between the Time Anomaly
agent and whatever system computes "what does a normal week look like
for this employee/placement/client?"

v1 ships :class:`HistoricalAverageProvider` — a SQL rolling-average
over the last N weeks of synced timesheets. When the Forecasting Agent
lands (deferred, see plan §4), it plugs in behind the same protocol
without the Time Anomaly agent needing to change.

Design decision (April 2 walkthrough): Group C is self-contained in v1.
No external forecasting dependency, no cross-agent coupling.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import Timesheet


@dataclass(frozen=True)
class Benchmark:
    """The typical-case expectation for a placement + pay period."""

    expected_regular_hours: float
    expected_overtime_hours: float
    expected_total_hours: float
    sample_size: int  # number of historical weeks used
    basis: str
    provider: str  # class name of the provider for traceability


class IBenchmarkProvider(Protocol):
    """Contract for "what does a normal week look like?" for a placement."""

    async def get_benchmark(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        placement_id: UUID,
        candidate_id: UUID | None,
        pay_period_end: date,
    ) -> Benchmark | None:
        """Return the benchmark, or ``None`` if there's not enough history.

        ``None`` means the detect stage should skip Group C for this cycle
        rather than firing a spurious alert against an empty baseline.
        """
        ...


class HistoricalAverageProvider:
    """Rolling average over the last ``lookback_weeks`` of synced timesheets.

    Basis options:

    - ``employee_history``: filter by candidate_id (default, most stable)
    - ``placement_history``: filter by placement_id
    - ``client_history``: filter by client via the placement join (future)

    Excludes the pay period under review and any rows whose ``status``
    indicates DidNotWork / Excluded so a previous anomaly doesn't pollute
    the baseline.
    """

    MIN_SAMPLE_SIZE = 3

    def __init__(self, *, lookback_weeks: int = 8, basis: str = "employee_history") -> None:
        if lookback_weeks < 1:
            raise ValueError("lookback_weeks must be >= 1")
        if basis not in ("employee_history", "placement_history", "client_history"):
            raise ValueError(f"Unsupported basis: {basis}")
        self._lookback_weeks = lookback_weeks
        self._basis = basis

    async def get_benchmark(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        placement_id: UUID,
        candidate_id: UUID | None,
        pay_period_end: date,
    ) -> Benchmark | None:
        window_start = pay_period_end - timedelta(weeks=self._lookback_weeks)

        conditions = [
            Timesheet.tenant_id == tenant_id,
            Timesheet.week_ending < pay_period_end,
            Timesheet.week_ending >= window_start,
            # Exclude statuses that indicate a previously-flagged week so a
            # corrected anomaly doesn't pull the baseline in either direction.
            Timesheet.status.notin_(("DidNotWork", "Excluded", "Rejected")),
        ]
        if self._basis == "employee_history" and candidate_id is not None:
            # Candidate matching uses name string today (no candidate_id on
            # Timesheet). When candidates have FK ids on Timesheet this
            # branch swaps to the foreign key.
            # TODO(josh): update once migration adds Timesheet.candidate_id.
            conditions.append(Timesheet.placement_id == placement_id)
        else:
            conditions.append(Timesheet.placement_id == placement_id)

        stmt = select(
            func.avg(Timesheet.regular_hours).label("reg"),
            func.avg(Timesheet.ot_hours).label("ot"),
            func.count(Timesheet.id).label("n"),
        ).where(and_(*conditions))

        row = (await session.execute(stmt)).one_or_none()
        if row is None or row.n is None or int(row.n) < self.MIN_SAMPLE_SIZE:
            return None

        reg = float(row.reg or 0)
        ot = float(row.ot or 0)
        return Benchmark(
            expected_regular_hours=reg,
            expected_overtime_hours=ot,
            expected_total_hours=reg + ot,
            sample_size=int(row.n),
            basis=self._basis,
            provider=type(self).__name__,
        )
