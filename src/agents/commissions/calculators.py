"""Commissions calculators — compute recruiter/sales incentives."""
from __future__ import annotations
from typing import Any

def calculate_placements_commissions(
    placements: list[dict[str, Any]],
    config: Any,
) -> list[dict[str, Any]]:
    """Calculate commissions for each placement based on margin/spread."""
    results = []
    
    for p in placements:
        pid = str(p.get("bullhorn_id") or p.get("id", ""))
        bill = float(p.get("bill_rate") or 0)
        pay = float(p.get("pay_rate") or 0)
        hours = float(p.get("hours_worked") or 0)
        spread = (bill - pay) * hours
        
        if spread <= 0: continue
        
        # Calculate for recruiter
        recruiter = p.get("recruiter_name")
        recruiter_rate = config.default_recruiter_rate_pct / 100.0
        recruiter_comm = spread * recruiter_rate
        
        # Calculate for sales
        sales_rep = p.get("sales_rep_name")
        sales_rate = config.default_sales_rate_pct / 100.0
        sales_comm = spread * sales_rate
        
        results.append({
            "placement_id": pid,
            "candidate_name": p.get("candidate_name"),
            "spread": round(spread, 2),
            "commissions": [
                {
                    "type": "recruiter",
                    "name": recruiter,
                    "amount": round(recruiter_comm, 2),
                    "rate_pct": config.default_recruiter_rate_pct,
                    "method": "percentage_of_spread"
                },
                {
                    "type": "sales",
                    "name": sales_rep,
                    "amount": round(sales_comm, 2),
                    "rate_pct": config.default_sales_rate_pct,
                    "method": "percentage_of_spread"
                }
            ]
        })
        
    return results
