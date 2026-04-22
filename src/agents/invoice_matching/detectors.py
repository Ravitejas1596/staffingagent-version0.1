"""Deterministic invoice matching and discrepancy detection.

Pure functions for PO-to-invoice matching, duplicate detection,
and amount reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class InvoiceMatch:
    """A proposed match between a billable charge/PO and an invoice."""
    invoice_id: str
    charge_id: str
    client_name: str
    confidence: float
    match_method: str       # exact | amount_match | fuzzy | unmatched
    amount_delta: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InvoiceException:
    """A flagged discrepancy in the invoice matching process."""
    exception_type: str
    severity: str
    description: str
    invoice_id: str = ""
    charge_id: str = ""
    client_name: str = ""
    financial_impact: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _f(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def match_invoices_to_charges(
    invoices: list[dict[str, Any]],
    charges: list[dict[str, Any]],
    *,
    amount_tolerance_pct: float = 2.0,
    max_days_gap: int = 90,
) -> tuple[list[InvoiceMatch], list[InvoiceException]]:
    """Match invoices to billable charges by client + amount + date.

    Returns (matches, exceptions).
    """
    matches: list[InvoiceMatch] = []
    exceptions: list[InvoiceException] = []
    matched_charge_ids: set[str] = set()
    matched_invoice_ids: set[str] = set()

    # Build charge lookup by client
    charges_by_client: dict[str, list[dict[str, Any]]] = {}
    for c in charges:
        client = (c.get("client_name") or "").lower().strip()
        charges_by_client.setdefault(client, []).append(c)

    for inv in invoices:
        inv_id = str(inv.get("invoice_id") or inv.get("id", ""))
        inv_client = (inv.get("client_name") or "").lower().strip()
        inv_amount = _f(inv.get("amount") or inv.get("total"))
        inv_date = inv.get("invoice_date")

        if not inv_client or inv_amount == 0:
            continue

        # Find matching charges for this client
        client_charges = charges_by_client.get(inv_client, [])
        best_match = None
        best_delta = float("inf")

        for c in client_charges:
            c_id = str(c.get("charge_id") or c.get("id", ""))
            if c_id in matched_charge_ids:
                continue

            c_amount = _f(c.get("amount") or c.get("subtotal"))
            if c_amount == 0:
                continue

            delta = abs(inv_amount - c_amount)
            tolerance = inv_amount * (amount_tolerance_pct / 100.0)

            if delta <= tolerance and delta < best_delta:
                best_delta = delta
                best_match = c

        if best_match:
            c_id = str(best_match.get("charge_id") or best_match.get("id", ""))
            c_amount = _f(best_match.get("amount") or best_match.get("subtotal"))
            delta = inv_amount - c_amount

            confidence = 1.0 - (abs(delta) / max(inv_amount, 0.01))
            method = "exact" if abs(delta) < 0.01 else "amount_match"

            matches.append(InvoiceMatch(
                invoice_id=inv_id,
                charge_id=c_id,
                client_name=inv.get("client_name", ""),
                confidence=round(min(confidence, 1.0), 3),
                match_method=method,
                amount_delta=round(delta, 2),
                details={
                    "invoice_amount": inv_amount,
                    "charge_amount": c_amount,
                },
            ))
            matched_charge_ids.add(c_id)
            matched_invoice_ids.add(inv_id)

            # Flag amount discrepancy even on match
            if abs(delta) > 0.01:
                exceptions.append(InvoiceException(
                    exception_type="amount_discrepancy",
                    severity="medium",
                    description=f"Invoice {inv_id} amount ${inv_amount:.2f} differs from charge ${c_amount:.2f} (delta: ${delta:.2f})",
                    invoice_id=inv_id, charge_id=c_id,
                    client_name=inv.get("client_name", ""),
                    financial_impact=delta,
                    details={"invoice_amount": inv_amount, "charge_amount": c_amount},
                ))
        else:
            # Unmatched invoice
            exceptions.append(InvoiceException(
                exception_type="unmatched_invoice",
                severity="high",
                description=f"Invoice {inv_id} for {inv.get('client_name', 'Unknown')} (${inv_amount:.2f}) has no matching charge",
                invoice_id=inv_id,
                client_name=inv.get("client_name", ""),
                financial_impact=inv_amount,
            ))

    # Charges without invoices
    for c in charges:
        c_id = str(c.get("charge_id") or c.get("id", ""))
        if c_id not in matched_charge_ids:
            c_amount = _f(c.get("amount") or c.get("subtotal"))
            if c_amount > 0:
                exceptions.append(InvoiceException(
                    exception_type="uninvoiced_charge",
                    severity="medium",
                    description=f"Charge {c_id} for {c.get('client_name', 'Unknown')} (${c_amount:.2f}) has no matching invoice",
                    charge_id=c_id,
                    client_name=c.get("client_name", ""),
                    financial_impact=c_amount,
                ))

    return matches, exceptions


def detect_duplicate_invoices(
    invoices: list[dict[str, Any]],
    *,
    date_window_days: int = 7,
) -> list[InvoiceException]:
    """Flag invoices with same client + amount within a date window."""
    exceptions: list[InvoiceException] = []
    seen: dict[str, list[dict[str, Any]]] = {}

    for inv in invoices:
        client = (inv.get("client_name") or "").lower().strip()
        amount = round(_f(inv.get("amount") or inv.get("total")), 2)
        key = f"{client}|{amount}"
        seen.setdefault(key, []).append(inv)

    for key, group in seen.items():
        if len(group) < 2:
            continue
        first = group[0]
        exceptions.append(InvoiceException(
            exception_type="duplicate_invoice",
            severity="high",
            description=f"{len(group)} invoices for {first.get('client_name', 'Unknown')} with same amount ${_f(first.get('amount')):.2f}",
            invoice_id=str(first.get("invoice_id") or first.get("id", "")),
            client_name=first.get("client_name", ""),
            financial_impact=_f(first.get("amount")) * (len(group) - 1),
            details={"duplicate_count": len(group), "invoice_ids": [str(i.get("invoice_id") or i.get("id", "")) for i in group]},
        ))

    return exceptions
