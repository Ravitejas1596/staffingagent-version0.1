"""Deterministic compliance detection rules.

Pure functions for credential expiry, overtime classification,
contract term validation, and worker classification checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class ComplianceViolation:
    """A detected compliance issue."""
    violation_type: str
    severity: str           # critical | high | medium | low
    description: str
    entity_type: str        # placement | candidate | credential
    entity_id: str
    entity_name: str = ""
    recommended_action: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _f(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def check_credential_expiry(
    credentials: list[dict[str, Any]],
    *,
    warning_days: int = 30,
    critical_days: int = 7,
    today: date | None = None,
) -> list[ComplianceViolation]:
    """Flag credentials expiring soon or already expired."""
    if today is None:
        today = date.today()
    violations: list[ComplianceViolation] = []

    for cred in credentials:
        cred_id = str(cred.get("id", ""))
        name = cred.get("candidate_name", "Unknown")
        cred_type = cred.get("credential_type", "Unknown")
        expiry = cred.get("expiry_date") or cred.get("expiration_date")

        if not expiry:
            continue
        try:
            exp_date = expiry if isinstance(expiry, date) else date.fromisoformat(str(expiry)[:10])
        except (ValueError, TypeError):
            continue

        days_until = (exp_date - today).days

        if days_until < 0:
            violations.append(ComplianceViolation(
                violation_type="credential_expired",
                severity="critical",
                description=f"{cred_type} for {name} expired {abs(days_until)} days ago",
                entity_type="credential", entity_id=cred_id, entity_name=name,
                recommended_action="Immediately notify candidate and suspend active assignments",
                details={"credential_type": cred_type, "expiry_date": str(exp_date), "days_expired": abs(days_until)},
            ))
        elif days_until <= critical_days:
            violations.append(ComplianceViolation(
                violation_type="credential_expiring_critical",
                severity="high",
                description=f"{cred_type} for {name} expires in {days_until} days",
                entity_type="credential", entity_id=cred_id, entity_name=name,
                recommended_action="Urgent: contact candidate for renewal",
                details={"credential_type": cred_type, "expiry_date": str(exp_date), "days_remaining": days_until},
            ))
        elif days_until <= warning_days:
            violations.append(ComplianceViolation(
                violation_type="credential_expiring_warning",
                severity="medium",
                description=f"{cred_type} for {name} expires in {days_until} days",
                entity_type="credential", entity_id=cred_id, entity_name=name,
                recommended_action="Send renewal reminder to candidate",
                details={"credential_type": cred_type, "expiry_date": str(exp_date), "days_remaining": days_until},
            ))

    return violations


def check_overtime_classification(
    placements: list[dict[str, Any]],
    *,
    ot_threshold_hours: float = 40.0,
) -> list[ComplianceViolation]:
    """Flag placements with OT where classification may be incorrect."""
    violations: list[ComplianceViolation] = []

    for p in placements:
        pid = str(p.get("bullhorn_id", ""))
        name = p.get("candidate_name", "Unknown")
        classification = (p.get("employee_type") or p.get("classification") or "").lower()
        total_hours = _f(p.get("total_hours") or p.get("hours_worked"))
        ot_hours = _f(p.get("ot_hours"))

        # Exempt worker with OT hours
        if "exempt" in classification and ot_hours > 0:
            violations.append(ComplianceViolation(
                violation_type="exempt_with_overtime",
                severity="high",
                description=f"Exempt worker {name} has {ot_hours}h OT — verify FLSA classification",
                entity_type="placement", entity_id=pid, entity_name=name,
                recommended_action="Review FLSA exempt classification for this role",
                details={"classification": classification, "ot_hours": ot_hours},
            ))

        # Non-exempt over threshold without OT recorded
        if total_hours > ot_threshold_hours and ot_hours == 0 and "exempt" not in classification:
            violations.append(ComplianceViolation(
                violation_type="missing_overtime",
                severity="medium",
                description=f"{name} worked {total_hours}h but no OT recorded — verify",
                entity_type="placement", entity_id=pid, entity_name=name,
                recommended_action="Verify timesheet has correct OT calculation",
                details={"total_hours": total_hours, "ot_threshold": ot_threshold_hours},
            ))

    return violations


def check_contract_terms(
    placements: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> list[ComplianceViolation]:
    """Flag placements exceeding contract limits."""
    if today is None:
        today = date.today()
    violations: list[ComplianceViolation] = []

    for p in placements:
        pid = str(p.get("bullhorn_id", ""))
        name = p.get("candidate_name", "Unknown")
        start = p.get("start_date")
        max_months = p.get("contract_max_months") or p.get("max_duration_months")
        max_hours = p.get("contract_max_hours")
        total_hours = _f(p.get("cumulative_hours", 0))

        # Duration check
        if start and max_months:
            try:
                start_dt = start if isinstance(start, date) else date.fromisoformat(str(start)[:10])
                months_elapsed = (today.year - start_dt.year) * 12 + (today.month - start_dt.month)
                max_m = int(max_months)
                if months_elapsed > max_m:
                    violations.append(ComplianceViolation(
                        violation_type="contract_duration_exceeded",
                        severity="high",
                        description=f"{name} has been on assignment {months_elapsed} months — contract max is {max_m}",
                        entity_type="placement", entity_id=pid, entity_name=name,
                        recommended_action="Review for extension or end-of-assignment processing",
                        details={"months_elapsed": months_elapsed, "max_months": max_m},
                    ))
            except (ValueError, TypeError):
                pass

        # Hours cap check
        if max_hours and total_hours > 0:
            max_h = _f(max_hours)
            if max_h > 0 and total_hours > max_h:
                violations.append(ComplianceViolation(
                    violation_type="contract_hours_exceeded",
                    severity="high",
                    description=f"{name} has worked {total_hours:.0f}h — contract max is {max_h:.0f}h",
                    entity_type="placement", entity_id=pid, entity_name=name,
                    recommended_action="Halt billing and process extension or new SOW",
                    details={"total_hours": total_hours, "max_hours": max_h},
                ))

    return violations


def check_worker_classification(
    placements: list[dict[str, Any]],
) -> list[ComplianceViolation]:
    """Flag potential worker misclassification risks (1099 vs W2)."""
    violations: list[ComplianceViolation] = []

    for p in placements:
        pid = str(p.get("bullhorn_id", ""))
        name = p.get("candidate_name", "Unknown")
        emp_type = (p.get("employee_type") or p.get("employment_type") or "").lower()
        duration_months = p.get("duration_months", 0)
        is_exclusive = p.get("is_exclusive", False)

        # 1099 contractor with long tenure is a misclassification risk
        if "1099" in emp_type or "contractor" in emp_type:
            risk_factors = []
            if _f(duration_months) > 12:
                risk_factors.append(f"tenure {int(duration_months)} months")
            if is_exclusive:
                risk_factors.append("exclusive engagement")

            if risk_factors:
                violations.append(ComplianceViolation(
                    violation_type="worker_misclassification_risk",
                    severity="medium",
                    description=f"1099 worker {name} has risk factors: {', '.join(risk_factors)}",
                    entity_type="placement", entity_id=pid, entity_name=name,
                    recommended_action="Review IRS 20-factor test for worker classification",
                    details={"employment_type": emp_type, "risk_factors": risk_factors},
                ))

    return violations
