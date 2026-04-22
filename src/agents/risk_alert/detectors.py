"""Detection rules for the Risk Alert agent.

Each detector is a pure function that accepts placement/charge data and
config thresholds, returning a list of ``RiskCandidate`` objects. No DB
access, no side effects — trivially unit-testable.

Risk categories (from product spec):
  - Placements: active/inactive date mismatches
  - Rates: below federal/state min wage, high pay/bill rate
  - Markup: negative, low, high
  - Amounts: high pay/bill, pay-no-bill, bill-no-pay, negative
  - Hours: pay ≠ bill hours, rate card mismatch
  - Duplicates: duplicate charge identification
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.agents.risk_alert.state_wages import FEDERAL_MIN_WAGE, get_min_wage


@dataclass(frozen=True)
class RiskCandidate:
    """A detector's proposal that a risk should be flagged."""
    risk_type: str
    severity: str
    description: str
    placement_id: str = ""
    candidate_name: str = ""
    financial_impact: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _f(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


# ── Placement Date Mismatches ──────────────────────────────────────


def detect_placement_mismatches(
    placements: list[dict[str, Any]],
    *,
    approved_statuses: list[str],
    inactive_statuses: list[str],
    today: date | None = None,
) -> list[RiskCandidate]:
    """Flag placements where dates don't align with status."""
    if today is None:
        today = date.today()
    risks: list[RiskCandidate] = []
    approved_lower = {s.lower().strip() for s in approved_statuses}
    inactive_lower = {s.lower().strip() for s in inactive_statuses}

    for p in placements:
        pid = str(p.get("bullhorn_id", ""))
        name = p.get("candidate_name", "Unknown")
        status = (p.get("status") or "").lower().strip()
        start = p.get("start_date")
        end = p.get("end_date")

        # Active placement with end date in the past
        if status in approved_lower and end:
            try:
                end_dt = end if isinstance(end, date) else date.fromisoformat(str(end)[:10])
                if end_dt < today:
                    risks.append(RiskCandidate(
                        risk_type="active_placement_date_mismatch",
                        severity="medium",
                        description=f"Active placement for {name} has end date {end_dt} in the past",
                        placement_id=pid, candidate_name=name,
                        details={"status": status, "end_date": str(end_dt)},
                    ))
            except (ValueError, TypeError):
                pass

        # Inactive placement with end date in the future
        if status in inactive_lower and end:
            try:
                end_dt = end if isinstance(end, date) else date.fromisoformat(str(end)[:10])
                if end_dt > today:
                    risks.append(RiskCandidate(
                        risk_type="inactive_placement_date_mismatch",
                        severity="medium",
                        description=f"Inactive placement for {name} has end date {end_dt} in the future",
                        placement_id=pid, candidate_name=name,
                        details={"status": status, "end_date": str(end_dt)},
                    ))
            except (ValueError, TypeError):
                pass

    return risks


# ── Rate Violations ────────────────────────────────────────────────


def detect_rate_violations(
    placements: list[dict[str, Any]],
    *,
    federal_min_wage: float = FEDERAL_MIN_WAGE,
    high_pay_rate: float = 150.0,
    high_bill_rate: float = 225.0,
    state_wage_overrides: dict[str, float] | None = None,
) -> list[RiskCandidate]:
    """Flag rate violations: below min wage (federal + state), high rates."""
    risks: list[RiskCandidate] = []
    for p in placements:
        pid = str(p.get("bullhorn_id", ""))
        name = p.get("candidate_name", "Unknown")
        pay = _f(p.get("pay_rate"))
        bill = _f(p.get("bill_rate"))
        state = p.get("state") or p.get("work_state") or ""

        if pay > 0:
            # Below federal minimum wage
            if pay < federal_min_wage:
                risks.append(RiskCandidate(
                    risk_type="below_federal_min_wage",
                    severity="high",
                    description=f"Pay rate ${pay:.2f}/hr below federal min ${federal_min_wage:.2f} for {name}",
                    placement_id=pid, candidate_name=name,
                    details={"pay_rate": pay, "federal_min": federal_min_wage},
                ))

            # Below state minimum wage
            if state:
                state_min = get_min_wage(state, overrides=state_wage_overrides)
                if state_min > federal_min_wage and pay < state_min:
                    risks.append(RiskCandidate(
                        risk_type="below_state_min_wage",
                        severity="high",
                        description=f"Pay rate ${pay:.2f}/hr below {state} min ${state_min:.2f} for {name}",
                        placement_id=pid, candidate_name=name,
                        details={"pay_rate": pay, "state": state, "state_min": state_min},
                    ))

            # High pay rate
            if pay > high_pay_rate:
                risks.append(RiskCandidate(
                    risk_type="high_pay_rate",
                    severity="medium",
                    description=f"High pay rate ${pay:.2f}/hr for {name} — verify against contract",
                    placement_id=pid, candidate_name=name,
                    details={"pay_rate": pay, "threshold": high_pay_rate},
                ))

        if bill > 0 and bill > high_bill_rate:
            risks.append(RiskCandidate(
                risk_type="high_bill_rate",
                severity="medium",
                description=f"High bill rate ${bill:.2f}/hr for {name} — verify against contract",
                placement_id=pid, candidate_name=name,
                details={"bill_rate": bill, "threshold": high_bill_rate},
            ))

    return risks


# ── Markup Violations ──────────────────────────────────────────────


def detect_markup_violations(
    placements: list[dict[str, Any]],
    *,
    low_markup_pct: float = 10.0,
    high_markup_pct: float = 250.0,
) -> list[RiskCandidate]:
    """Flag negative, low, and high markup percentages."""
    risks: list[RiskCandidate] = []
    for p in placements:
        pid = str(p.get("bullhorn_id", ""))
        name = p.get("candidate_name", "Unknown")
        pay = _f(p.get("pay_rate"))
        bill = _f(p.get("bill_rate"))

        if pay <= 0 or bill <= 0:
            continue

        markup = (bill - pay) / pay * 100

        if markup < 0:
            risks.append(RiskCandidate(
                risk_type="negative_markup",
                severity="high",
                description=f"Negative markup ({markup:.1f}%) — paying more than billing for {name}",
                placement_id=pid, candidate_name=name,
                financial_impact=round(pay - bill, 2),
                details={"markup_pct": round(markup, 2), "pay_rate": pay, "bill_rate": bill},
            ))
        elif markup < low_markup_pct:
            risks.append(RiskCandidate(
                risk_type="low_markup",
                severity="medium",
                description=f"Low markup ({markup:.1f}%) for {name} — below {low_markup_pct}% threshold",
                placement_id=pid, candidate_name=name,
                details={"markup_pct": round(markup, 2), "threshold": low_markup_pct},
            ))
        elif markup > high_markup_pct:
            risks.append(RiskCandidate(
                risk_type="high_markup",
                severity="medium",
                description=f"High markup ({markup:.1f}%) for {name} — above {high_markup_pct}% threshold",
                placement_id=pid, candidate_name=name,
                details={"markup_pct": round(markup, 2), "threshold": high_markup_pct},
            ))

    return risks


# ── Amount Anomalies ───────────────────────────────────────────────


def detect_amount_anomalies(
    charges: list[dict[str, Any]],
    *,
    high_pay_amount: float = 5000.0,
    high_bill_amount: float = 7500.0,
) -> list[RiskCandidate]:
    """Flag amount issues: high, negative, pay-no-bill, bill-no-pay."""
    risks: list[RiskCandidate] = []
    for c in charges:
        pid = str(c.get("placement_id") or c.get("bullhorn_id", ""))
        name = c.get("candidate_name", "Unknown")
        ts_id = str(c.get("timesheet_id", ""))
        pay_amt = _f(c.get("pay_amount"))
        bill_amt = _f(c.get("bill_amount"))

        base = {"timesheet_id": ts_id, "placement_id": pid}

        # Negative amounts
        if pay_amt < 0:
            risks.append(RiskCandidate(
                risk_type="negative_pay_amount", severity="high",
                description=f"Negative pay amount ${pay_amt:.2f} for {name}",
                placement_id=pid, candidate_name=name,
                financial_impact=pay_amt, details={**base, "pay_amount": pay_amt},
            ))
        if bill_amt < 0:
            risks.append(RiskCandidate(
                risk_type="negative_bill_amount", severity="high",
                description=f"Negative bill amount ${bill_amt:.2f} for {name}",
                placement_id=pid, candidate_name=name,
                financial_impact=bill_amt, details={**base, "bill_amount": bill_amt},
            ))

        # High amounts
        if pay_amt > high_pay_amount:
            risks.append(RiskCandidate(
                risk_type="high_pay_amount", severity="medium",
                description=f"High pay amount ${pay_amt:.2f} for {name} — exceeds ${high_pay_amount:.0f}",
                placement_id=pid, candidate_name=name,
                details={**base, "pay_amount": pay_amt, "threshold": high_pay_amount},
            ))
        if bill_amt > high_bill_amount:
            risks.append(RiskCandidate(
                risk_type="high_bill_amount", severity="medium",
                description=f"High bill amount ${bill_amt:.2f} for {name} — exceeds ${high_bill_amount:.0f}",
                placement_id=pid, candidate_name=name,
                details={**base, "bill_amount": bill_amt, "threshold": high_bill_amount},
            ))

        # Pay with no bill / bill with no pay
        if pay_amt > 0 and bill_amt == 0:
            risks.append(RiskCandidate(
                risk_type="pay_no_bill", severity="medium",
                description=f"Pay amount ${pay_amt:.2f} with no bill amount for {name}",
                placement_id=pid, candidate_name=name,
                financial_impact=pay_amt, details={**base, "pay_amount": pay_amt},
            ))
        if bill_amt > 0 and pay_amt == 0:
            risks.append(RiskCandidate(
                risk_type="bill_no_pay", severity="medium",
                description=f"Bill amount ${bill_amt:.2f} with no pay amount for {name}",
                placement_id=pid, candidate_name=name,
                details={**base, "bill_amount": bill_amt},
            ))

    return risks


# ── Hours Mismatches ───────────────────────────────────────────────


def detect_hours_mismatches(
    charges: list[dict[str, Any]],
    *,
    bill_rate_mismatch_pct: float = 20.0,
) -> list[RiskCandidate]:
    """Flag pay≠bill hours and transaction rate vs placement rate card."""
    risks: list[RiskCandidate] = []
    for c in charges:
        pid = str(c.get("placement_id") or c.get("bullhorn_id", ""))
        name = c.get("candidate_name", "Unknown")
        ts_id = str(c.get("timesheet_id", ""))
        pay_hours = _f(c.get("pay_hours"))
        bill_hours = _f(c.get("bill_hours"))
        transaction_pay_rate = _f(c.get("transaction_pay_rate"))
        transaction_bill_rate = _f(c.get("transaction_bill_rate"))
        placement_pay_rate = _f(c.get("placement_pay_rate") or c.get("pay_rate"))
        placement_bill_rate = _f(c.get("placement_bill_rate") or c.get("bill_rate"))

        base = {"timesheet_id": ts_id, "placement_id": pid}

        # Pay ≠ Bill Hours
        if pay_hours > 0 and bill_hours > 0 and abs(pay_hours - bill_hours) > 0.01:
            risks.append(RiskCandidate(
                risk_type="pay_bill_hours_mismatch", severity="medium",
                description=f"Pay hours ({pay_hours}) ≠ Bill hours ({bill_hours}) for {name}",
                placement_id=pid, candidate_name=name,
                details={**base, "pay_hours": pay_hours, "bill_hours": bill_hours},
            ))

        # Transaction rate differs from placement rate card
        if placement_pay_rate > 0 and transaction_pay_rate > 0:
            pct_diff = abs(transaction_pay_rate - placement_pay_rate) / placement_pay_rate * 100
            if pct_diff > bill_rate_mismatch_pct:
                risks.append(RiskCandidate(
                    risk_type="pay_rate_card_mismatch", severity="medium",
                    description=f"Transaction pay rate ${transaction_pay_rate:.2f} differs {pct_diff:.0f}% from placement rate ${placement_pay_rate:.2f} for {name}",
                    placement_id=pid, candidate_name=name,
                    details={**base, "transaction_rate": transaction_pay_rate, "placement_rate": placement_pay_rate, "pct_diff": round(pct_diff, 1)},
                ))

        if placement_bill_rate > 0 and transaction_bill_rate > 0:
            pct_diff = abs(transaction_bill_rate - placement_bill_rate) / placement_bill_rate * 100
            if pct_diff > bill_rate_mismatch_pct:
                risks.append(RiskCandidate(
                    risk_type="bill_rate_card_mismatch", severity="medium",
                    description=f"Transaction bill rate ${transaction_bill_rate:.2f} differs {pct_diff:.0f}% from placement rate ${placement_bill_rate:.2f} for {name}",
                    placement_id=pid, candidate_name=name,
                    details={**base, "transaction_rate": transaction_bill_rate, "placement_rate": placement_bill_rate, "pct_diff": round(pct_diff, 1)},
                ))

    return risks


# ── Duplicate Charge Identification ────────────────────────────────


def detect_duplicate_charges(
    charges: list[dict[str, Any]],
) -> list[RiskCandidate]:
    """Flag charges with same placement + period + amount."""
    risks: list[RiskCandidate] = []
    seen: dict[str, list[dict[str, Any]]] = {}

    for c in charges:
        pid = str(c.get("placement_id") or c.get("bullhorn_id", ""))
        period = str(c.get("period_end") or c.get("week_ending", ""))
        pay_amt = _f(c.get("pay_amount"))
        bill_amt = _f(c.get("bill_amount"))

        key = f"{pid}|{period}|{pay_amt:.2f}|{bill_amt:.2f}"
        if key not in seen:
            seen[key] = []
        seen[key].append(c)

    for key, group in seen.items():
        if len(group) < 2:
            continue
        first = group[0]
        pid = str(first.get("placement_id") or first.get("bullhorn_id", ""))
        name = first.get("candidate_name", "Unknown")
        risks.append(RiskCandidate(
            risk_type="duplicate_charge", severity="high",
            description=f"{len(group)} duplicate charges detected for {name} in same period",
            placement_id=pid, candidate_name=name,
            financial_impact=_f(first.get("pay_amount")) * (len(group) - 1),
            details={
                "duplicate_count": len(group),
                "charge_ids": [str(c.get("id", "")) for c in group],
            },
        ))

    return risks
