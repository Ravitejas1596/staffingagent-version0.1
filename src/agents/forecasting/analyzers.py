"""Forecasting analyzers — process historical data for trend analysis."""
from __future__ import annotations
from typing import Any
from datetime import date, timedelta

def process_historical_trends(
    billing_history: list[dict[str, Any]],
    payroll_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize billing and payroll by week/month for trend analysis."""
    summary = {}
    
    # Process billing
    for b in billing_history:
        period = str(b.get("period_end") or b.get("week_ending", ""))
        amount = float(b.get("amount") or 0)
        if period not in summary:
            summary[period] = {"billing": 0.0, "payroll": 0.0, "placement_count": 0}
        summary[period]["billing"] += amount
        if b.get("placement_id"):
            summary[period]["placement_count"] += 1
            
    # Process payroll
    for p in payroll_history:
        period = str(p.get("period_end") or p.get("week_ending", ""))
        amount = float(p.get("amount") or 0)
        if period not in summary:
            summary[period] = {"billing": 0.0, "payroll": 0.0, "placement_count": 0}
        summary[period]["payroll"] += amount

    # Convert to sorted list
    sorted_data = sorted([{"period": k, **v} for k, v in summary.items()], key=lambda x: x["period"])
    
    # Simple rolling average calculation
    for i in range(len(sorted_data)):
        window = sorted_data[max(0, i-3):i+1]
        sorted_data[i]["billing_rolling_avg"] = sum(x["billing"] for x in window) / len(window)
        sorted_data[i]["margin_pct"] = (
            (sorted_data[i]["billing"] - sorted_data[i]["payroll"]) / sorted_data[i]["billing"] * 100
            if sorted_data[i]["billing"] > 0 else 0
        )

    return {
        "time_series": sorted_data,
        "total_revenue": sum(x["billing"] for x in sorted_data),
        "avg_margin": sum(x["margin_pct"] for x in sorted_data) / len(sorted_data) if sorted_data else 0,
        "growth_trend": (
            (sorted_data[-1]["billing"] - sorted_data[0]["billing"]) / sorted_data[0]["billing"]
            if len(sorted_data) > 1 and sorted_data[0]["billing"] > 0 else 0
        )
    }
