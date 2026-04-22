"""Payroll reconciliation detectors — match payroll records to payable charges."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class PayrollDiscrepancy:
    discrepancy_type: str
    severity: str
    description: str
    payroll_id: str = ""
    charge_id: str = ""
    candidate_name: str = ""
    financial_impact: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

def _f(v: Any) -> float:
    try: return float(v) if v is not None else 0.0
    except (TypeError, ValueError): return 0.0

def reconcile_payroll_to_charges(
    payroll_records: list[dict[str, Any]],
    charges: list[dict[str, Any]],
    *, amount_tolerance_pct: float = 0.5,
) -> tuple[list[dict[str, Any]], list[PayrollDiscrepancy]]:
    """Match payroll entries to expected payable charges."""
    matches, discrepancies = [], []
    matched_charge_ids: set[str] = set()

    # Build charge lookup by candidate + period
    charges_by_key: dict[str, dict] = {}
    for c in charges:
        candidate = (c.get("candidate_name") or "").lower().strip()
        period = str(c.get("period_end") or c.get("week_ending", ""))
        key = f"{candidate}|{period}"
        charges_by_key[key] = c

    for pr in payroll_records:
        pr_id = str(pr.get("payroll_id") or pr.get("id", ""))
        name = (pr.get("candidate_name") or "").lower().strip()
        period = str(pr.get("period_end") or pr.get("week_ending", ""))
        pr_amount = _f(pr.get("gross_pay") or pr.get("amount"))
        
        key = f"{name}|{period}"
        charge = charges_by_key.get(key)
        
        if charge:
            c_id = str(charge.get("charge_id") or charge.get("id", ""))
            c_amount = _f(charge.get("amount") or charge.get("payable_amount"))
            delta = pr_amount - c_amount
            tolerance = abs(c_amount) * (amount_tolerance_pct / 100.0) if c_amount else 1.0

            matches.append({"payroll_id": pr_id, "charge_id": c_id, "payroll_amount": pr_amount,
                            "charge_amount": c_amount, "delta": round(delta, 2)})
            matched_charge_ids.add(c_id)

            if abs(delta) > tolerance:
                discrepancies.append(PayrollDiscrepancy(
                    discrepancy_type="pay_amount_mismatch", 
                    severity="high" if abs(delta) > 100 else "medium",
                    description=f"Payroll for {name} (${pr_amount:.2f}) ≠ expected payable (${c_amount:.2f})",
                    payroll_id=pr_id, charge_id=c_id, candidate_name=name, financial_impact=delta,
                    details={"payroll_amount": pr_amount, "charge_amount": c_amount},
                ))
        else:
            discrepancies.append(PayrollDiscrepancy(
                discrepancy_type="unmatched_payroll_entry", severity="high",
                description=f"Payroll record for {name} (${pr_amount:.2f}) has no matching payable charge",
                payroll_id=pr_id, candidate_name=name, financial_impact=pr_amount,
                details={"period": period},
            ))

    for c in charges:
        c_id = str(c.get("charge_id") or c.get("id", ""))
        if c_id not in matched_charge_ids:
            c_amount = _f(c.get("amount") or c.get("payable_amount"))
            name = c.get("candidate_name", "Unknown")
            if c_amount > 0:
                discrepancies.append(PayrollDiscrepancy(
                    discrepancy_type="missing_payment", severity="critical",
                    description=f"Expected payment of ${c_amount:.2f} for {name} is missing from payroll",
                    charge_id=c_id, candidate_name=name, financial_impact=-c_amount,
                ))

    return matches, discrepancies
