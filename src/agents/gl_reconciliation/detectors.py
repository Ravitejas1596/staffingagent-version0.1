"""GL Reconciliation detectors — match GL entries to charges, find discrepancies."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class GLDiscrepancy:
    discrepancy_type: str
    severity: str
    description: str
    gl_entry_id: str = ""
    charge_id: str = ""
    financial_impact: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

def _f(v: Any) -> float:
    try: return float(v) if v is not None else 0.0
    except (TypeError, ValueError): return 0.0

def reconcile_gl_to_charges(
    gl_entries: list[dict[str, Any]],
    charges: list[dict[str, Any]],
    *, amount_tolerance_pct: float = 1.0,
) -> tuple[list[dict[str, Any]], list[GLDiscrepancy]]:
    """Match GL entries to source charges. Returns (matches, discrepancies)."""
    matches, discrepancies = [], []
    matched_charge_ids: set[str] = set()
    matched_gl_ids: set[str] = set()

    charges_by_ref: dict[str, dict] = {}
    for c in charges:
        ref = str(c.get("reference") or c.get("charge_id") or c.get("id", ""))
        if ref: charges_by_ref[ref] = c

    for gl in gl_entries:
        gl_id = str(gl.get("gl_entry_id") or gl.get("id", ""))
        gl_ref = str(gl.get("reference") or gl.get("source_ref", ""))
        gl_amount = _f(gl.get("amount"))
        gl_account = gl.get("account", "")

        charge = charges_by_ref.get(gl_ref)
        if charge:
            c_id = str(charge.get("charge_id") or charge.get("id", ""))
            c_amount = _f(charge.get("amount") or charge.get("subtotal"))
            delta = gl_amount - c_amount
            tolerance = abs(c_amount) * (amount_tolerance_pct / 100.0) if c_amount else 1.0

            matches.append({"gl_entry_id": gl_id, "charge_id": c_id, "gl_amount": gl_amount,
                            "charge_amount": c_amount, "delta": round(delta, 2)})
            matched_charge_ids.add(c_id)
            matched_gl_ids.add(gl_id)

            if abs(delta) > tolerance:
                discrepancies.append(GLDiscrepancy(
                    discrepancy_type="amount_mismatch", severity="high",
                    description=f"GL entry {gl_id} amount ${gl_amount:.2f} ≠ charge ${c_amount:.2f} (delta ${delta:.2f})",
                    gl_entry_id=gl_id, charge_id=c_id, financial_impact=delta,
                    details={"gl_amount": gl_amount, "charge_amount": c_amount, "account": gl_account},
                ))
        else:
            discrepancies.append(GLDiscrepancy(
                discrepancy_type="orphaned_gl_entry", severity="medium",
                description=f"GL entry {gl_id} (${gl_amount:.2f}) has no matching source charge",
                gl_entry_id=gl_id, financial_impact=gl_amount,
                details={"reference": gl_ref, "account": gl_account},
            ))

    for c in charges:
        c_id = str(c.get("charge_id") or c.get("id", ""))
        if c_id not in matched_charge_ids:
            c_amount = _f(c.get("amount") or c.get("subtotal"))
            if c_amount != 0:
                discrepancies.append(GLDiscrepancy(
                    discrepancy_type="missing_gl_entry", severity="high",
                    description=f"Charge {c_id} (${c_amount:.2f}) has no GL posting",
                    charge_id=c_id, financial_impact=c_amount,
                ))

    # Duplicate GL check
    seen_keys: dict[str, list[str]] = {}
    for gl in gl_entries:
        ref = str(gl.get("reference", ""))
        amt = _f(gl.get("amount"))
        key = f"{ref}|{amt:.2f}"
        gl_id = str(gl.get("gl_entry_id") or gl.get("id", ""))
        seen_keys.setdefault(key, []).append(gl_id)
    for key, ids in seen_keys.items():
        if len(ids) >= 2:
            discrepancies.append(GLDiscrepancy(
                discrepancy_type="duplicate_gl_posting", severity="high",
                description=f"{len(ids)} duplicate GL postings for reference {key.split('|')[0]}",
                gl_entry_id=ids[0],
                details={"duplicate_ids": ids, "count": len(ids)},
            ))

    return matches, discrepancies
