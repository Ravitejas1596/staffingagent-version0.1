"""Deterministic AR prioritization and escalation path routing.

Pure functions — no DB access, no side effects. The Collections agent
runs these before (optionally) using LLM for draft message generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class ARPriority:
    """Scored AR record with priority tier and recommended action."""
    invoice_id: str
    client_name: str
    amount: float
    days_outstanding: int
    priority_score: float
    priority_tier: str        # critical | high | medium | low
    escalation_stage: str     # reminder | follow_up | escalation | legal
    recommended_action: str
    details: dict[str, Any] = field(default_factory=dict)


def _f(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _i(val: Any) -> int:
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def prioritize_ar(
    ar_records: list[dict[str, Any]],
    *,
    reminder_days: int = 15,
    followup_days: int = 30,
    escalation_days: int = 60,
    legal_days: int = 90,
    high_priority_amount: float = 10000.0,
    critical_priority_amount: float = 50000.0,
) -> list[ARPriority]:
    """Score and prioritize AR records by aging × amount × history.

    Priority score formula:
        base = days_outstanding / 30  (normalized to months)
        amount_factor = log2(amount / 1000 + 1)  (diminishing returns)
        score = base * amount_factor * history_multiplier

    Returns sorted by priority_score descending (most urgent first).
    """
    import math

    results: list[ARPriority] = []

    for rec in ar_records:
        inv_id = str(rec.get("invoice_id") or rec.get("bullhorn_id", ""))
        client = rec.get("client_name", "Unknown")
        amount = _f(rec.get("amount") or rec.get("balance"))
        days = _i(rec.get("days_outstanding"))
        payment_history = rec.get("payment_history_score", 1.0)

        if amount <= 0 or days <= 0:
            continue

        # Score calculation
        base = days / 30.0
        amount_factor = math.log2(amount / 1000.0 + 1) if amount > 0 else 0
        history_mult = 2.0 - min(max(_f(payment_history), 0.0), 1.0)
        score = round(base * amount_factor * history_mult, 2)

        # Escalation stage
        if days >= legal_days:
            stage = "legal"
            action = f"Escalate to legal — {days} days outstanding, ${amount:,.2f}"
        elif days >= escalation_days:
            stage = "escalation"
            action = f"Escalate to management — {days} days outstanding, ${amount:,.2f}"
        elif days >= followup_days:
            stage = "follow_up"
            action = f"Send follow-up collection notice — {days} days outstanding"
        elif days >= reminder_days:
            stage = "reminder"
            action = f"Send payment reminder — {days} days past due"
        else:
            stage = "reminder"
            action = f"Monitor — {days} days outstanding"

        # Priority tier
        if amount >= critical_priority_amount or (days >= legal_days and amount >= high_priority_amount):
            tier = "critical"
        elif amount >= high_priority_amount or days >= escalation_days:
            tier = "high"
        elif days >= followup_days:
            tier = "medium"
        else:
            tier = "low"

        results.append(ARPriority(
            invoice_id=inv_id,
            client_name=client,
            amount=amount,
            days_outstanding=days,
            priority_score=score,
            priority_tier=tier,
            escalation_stage=stage,
            recommended_action=action,
            details={
                "payment_history_score": _f(payment_history),
                "base_score": round(base, 2),
                "amount_factor": round(amount_factor, 2),
            },
        ))

    results.sort(key=lambda r: r.priority_score, reverse=True)
    return results


def group_by_client(priorities: list[ARPriority]) -> dict[str, list[ARPriority]]:
    """Group prioritized AR by client for batch outreach."""
    groups: dict[str, list[ARPriority]] = {}
    for p in priorities:
        groups.setdefault(p.client_name, []).append(p)
    return groups
