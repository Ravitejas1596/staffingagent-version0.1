"""Contract compliance detectors — match placements to contractual terms."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any

@dataclass(frozen=True)
class ContractViolation:
    violation_type: str
    severity: str
    description: str
    placement_id: str
    candidate_name: str = ""
    details: dict[str, Any] = field(default_factory=dict)

def detect_contract_violations(
    placements: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    config: Any,
) -> list[ContractViolation]:
    """Flag placements that violate contractual terms."""
    violations = []
    
    # Build contract lookup by client
    contracts_by_client: dict[str, dict] = {}
    for c in contracts:
        client = (c.get("client_name") or "").lower().strip()
        contracts_by_client[client] = c

    today = date.today()

    for p in placements:
        pid = str(p.get("bullhorn_id") or p.get("id", ""))
        client = (p.get("client_name") or "").lower().strip()
        name = p.get("candidate_name", "Unknown")
        
        contract = contracts_by_client.get(client)
        if not contract: continue
        
        # Rate check
        max_rate = float(contract.get("max_bill_rate") or 0)
        actual_rate = float(p.get("bill_rate") or 0)
        if max_rate > 0 and actual_rate > max_rate:
            violations.append(ContractViolation(
                violation_type="rate_exceeds_contract",
                severity="high",
                description=f"Bill rate ${actual_rate:.2f} exceeds contract max ${max_rate:.2f} for {name}",
                placement_id=pid, candidate_name=name,
                details={"actual_rate": actual_rate, "max_rate": max_rate}
            ))
            
        # Tenure check
        start_date = p.get("start_date")
        if start_date:
            try:
                sd = start_date if isinstance(start_date, date) else date.fromisoformat(str(start_date)[:10])
                months_elapsed = (today.year - sd.year) * 12 + (today.month - sd.month)
                if months_elapsed > config.tenure_limit_months:
                    violations.append(ContractViolation(
                        violation_type="tenure_limit_exceeded",
                        severity="medium",
                        description=f"{name} has been on assignment {months_elapsed} months (limit {config.tenure_limit_months})",
                        placement_id=pid, candidate_name=name,
                        details={"months_elapsed": months_elapsed, "limit": config.tenure_limit_months}
                    ))
            except (ValueError, TypeError): pass

    return violations
