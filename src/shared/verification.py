"""
Reusable verification node for StaffingAgent LangGraph agents.

Every agent pipeline should include a verification step before output.
This module provides composable checks that can be wired into any graph
as a node — no separate "Verification Agent" needed at P0.

Verification types:
  1. math_check     — re-derive financial totals from source data
  2. record_count   — confirm no records were silently dropped
  3. temporal_check — timestamps are logically ordered
  4. field_presence — required output fields exist on every record
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VerificationResult(BaseModel):
    """Outcome of a single verification check."""

    check_type: str
    status: str = Field(description="PASS | FAIL | WARN")
    expected: str = ""
    actual: str = ""
    delta: Optional[float] = None
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


class VerificationReport(BaseModel):
    """Aggregated report from all verification checks on an agent output."""

    checks: list[VerificationResult] = Field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[VerificationResult]:
        return [c for c in self.checks if c.status == "FAIL"]

    @property
    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        return f"{passed}/{total} checks passed"


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def math_check(
    records: list[dict[str, Any]],
    *,
    amount_field: str = "total",
    expected_total: float,
    tolerance: float = 0.01,
) -> VerificationResult:
    """Re-sum *amount_field* across records and compare to *expected_total*."""
    actual_total = sum(float(r.get(amount_field, 0) or 0) for r in records)
    delta = abs(actual_total - expected_total)
    status = "PASS" if delta <= tolerance else "FAIL"
    return VerificationResult(
        check_type="math_check",
        status=status,
        expected=f"{expected_total:.2f}",
        actual=f"{actual_total:.2f}",
        delta=delta,
        detail=f"Sum of '{amount_field}' across {len(records)} records",
    )


def record_count_check(
    output_records: list[Any],
    *,
    expected_count: int,
) -> VerificationResult:
    """Verify no records were silently dropped during processing."""
    actual = len(output_records)
    status = "PASS" if actual == expected_count else "FAIL"
    return VerificationResult(
        check_type="record_count",
        status=status,
        expected=str(expected_count),
        actual=str(actual),
        detail="Output record count vs input record count",
    )


def temporal_check(
    records: list[dict[str, Any]],
    *,
    before_field: str,
    after_field: str,
    label: str = "",
) -> VerificationResult:
    """Verify that *before_field* timestamp <= *after_field* for all records.

    Accepts ISO-format strings or datetime objects.
    """
    violations: list[str] = []
    for r in records:
        before_val = r.get(before_field)
        after_val = r.get(after_field)
        if before_val is None or after_val is None:
            continue
        if isinstance(before_val, str):
            before_val = datetime.fromisoformat(before_val)
        if isinstance(after_val, str):
            after_val = datetime.fromisoformat(after_val)
        if before_val > after_val:
            record_id = r.get("placement_id") or r.get("id") or "?"
            violations.append(record_id)

    status = "PASS" if not violations else "FAIL"
    return VerificationResult(
        check_type="temporal_check",
        status=status,
        expected=f"{before_field} <= {after_field}",
        actual=f"{len(violations)} violations" if violations else "0 violations",
        detail=label or f"Temporal ordering: {before_field} before {after_field}",
    )


def field_presence_check(
    records: list[dict[str, Any]],
    *,
    required_fields: list[str],
) -> VerificationResult:
    """Verify every record contains all required output fields."""
    missing: list[str] = []
    for i, r in enumerate(records):
        for f in required_fields:
            if f not in r:
                record_id = r.get("placement_id") or r.get("id") or f"index={i}"
                missing.append(f"{record_id}.{f}")

    status = "PASS" if not missing else "FAIL"
    return VerificationResult(
        check_type="field_presence",
        status=status,
        expected=f"All records have {required_fields}",
        actual=f"{len(missing)} missing fields" if missing else "all present",
        detail="; ".join(missing[:10]) if missing else "",
    )


# ---------------------------------------------------------------------------
# Composable verification node for LangGraph
# ---------------------------------------------------------------------------

def run_verification(
    checks: list[VerificationResult],
    *,
    fail_action: str = "flag",
) -> VerificationReport:
    """Aggregate check results into a report and log outcome.

    Args:
        checks: list of individual VerificationResult objects.
        fail_action: "flag" (log + continue) or "reject" (raise on failure).
    """
    report = VerificationReport(checks=checks)
    if report.all_passed:
        logger.info("Verification PASSED — %s", report.summary)
    else:
        msg = f"Verification FAILED — {report.summary}: {[f.detail for f in report.failures]}"
        logger.warning(msg)
        if fail_action == "reject":
            raise ValueError(msg)
    return report
