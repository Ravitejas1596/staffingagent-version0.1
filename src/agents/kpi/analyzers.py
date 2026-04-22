"""KPI analyzers — compute performance metrics from raw data."""
from __future__ import annotations
from typing import Any

def compute_agency_kpis(
    metrics_data: dict[str, Any],
    config: Any,
) -> dict[str, Any]:
    """Compute top-level KPIs from aggregated platform data."""
    results = {}
    
    # Fill Rate
    jobs = metrics_data.get("job_orders", 0)
    placements = metrics_data.get("placements", 0)
    results["fill_rate"] = (placements / jobs * 100) if jobs > 0 else 0
    
    # Gross Margin
    revenue = metrics_data.get("total_billable", 0)
    cost = metrics_data.get("total_payable", 0)
    results["gross_margin_pct"] = ((revenue - cost) / revenue * 100) if revenue > 0 else 0
    
    # DSO (Days Sales Outstanding)
    total_ar = metrics_data.get("total_ar_balance", 0)
    avg_daily_sales = revenue / 30 if revenue > 0 else 1
    results["dso"] = total_ar / avg_daily_sales
    
    # Anomaly Detection
    anomalies = []
    if results["fill_rate"] < config.target_fill_rate_pct:
        anomalies.append({
            "metric": "fill_rate",
            "value": results["fill_rate"],
            "target": config.target_fill_rate_pct,
            "status": "underperforming"
        })
        
    if results["gross_margin_pct"] < config.target_margin_pct:
        anomalies.append({
            "metric": "gross_margin",
            "value": results["gross_margin_pct"],
            "target": config.target_margin_pct,
            "status": "underperforming"
        })

    if results["dso"] > config.max_dso_days:
        anomalies.append({
            "metric": "dso",
            "value": results["dso"],
            "target": config.max_dso_days,
            "status": "high"
        })

    return {
        "kpis": results,
        "anomalies": anomalies,
        "summary": f"Fill Rate: {results['fill_rate']:.1f}%, Margin: {results['gross_margin_pct']:.1f}%, DSO: {results['dso']:.1f} days"
    }
