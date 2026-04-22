"""US state minimum wage table for the Risk Alert agent.

Static table of all 50 states + DC minimum wages (2025 data).
Tenants can override per-state via the ``agent_settings`` table.
"""
from __future__ import annotations

FEDERAL_MIN_WAGE: float = 7.25

STATE_MIN_WAGES: dict[str, float] = {
    "AL": 7.25, "AK": 11.73, "AZ": 14.70, "AR": 11.00, "CA": 16.50,
    "CO": 14.81, "CT": 16.35, "DE": 13.25, "DC": 17.50, "FL": 14.00,
    "GA": 7.25, "HI": 14.00, "ID": 7.25, "IL": 14.00, "IN": 7.25,
    "IA": 7.25, "KS": 7.25, "KY": 7.25, "LA": 7.25, "ME": 14.65,
    "MD": 15.00, "MA": 15.00, "MI": 10.56, "MN": 11.13, "MS": 7.25,
    "MO": 13.75, "MT": 10.55, "NE": 13.50, "NV": 12.00, "NH": 7.25,
    "NJ": 15.49, "NM": 12.00, "NY": 15.50, "NC": 7.25, "ND": 7.25,
    "OH": 10.70, "OK": 7.25, "OR": 14.70, "PA": 7.25, "RI": 14.00,
    "SC": 7.25, "SD": 11.50, "TN": 7.25, "TX": 7.25, "UT": 7.25,
    "VT": 14.01, "VA": 12.41, "WA": 16.66, "WV": 8.75, "WI": 7.25,
    "WY": 7.25,
}


def get_min_wage(
    state: str | None,
    *,
    overrides: dict[str, float] | None = None,
) -> float:
    """Return the effective minimum wage for a US state.

    Resolution: tenant override → static table → federal fallback.
    """
    if not state:
        return FEDERAL_MIN_WAGE
    code = state.strip().upper()
    if overrides and code in overrides:
        return float(overrides[code])
    return STATE_MIN_WAGES.get(code, FEDERAL_MIN_WAGE)
