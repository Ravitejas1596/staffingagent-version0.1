"""
HubSpot pulse for CEO Daily Brief.

Fetches pipeline (deals), recent contacts, and marketing activity from HubSpot API.
Returns a structured markdown summary for the daily brief engine.

Requires: HUBSPOT_ACCESS_TOKEN, HUBSPOT_PORTAL_ID
Optional: HUBSPOT_FORM_GUID (for form submission context)
"""
from __future__ import annotations

import os
from datetime import datetime

from ..integrations.hubspot import PIPELINE_STAGES, search_contacts_recent, search_deals


def _format_date(ts: str | None) -> str:
    """Format HubSpot timestamp to readable date."""
    if not ts:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return str(ts)[:10] if ts else "Unknown"


def _stage_label(stage_id: str | None) -> str:
    """Map stage ID to human label."""
    if not stage_id:
        return "Unknown"
    return PIPELINE_STAGES.get(stage_id, stage_id.replace("_", " ").title())


def fetch_hubspot_pulse() -> str:
    """
    Fetch HubSpot data and return a markdown summary for the daily brief.

    Returns empty string if HUBSPOT_ACCESS_TOKEN is not set (graceful degradation).
    """
    if not os.environ.get("HUBSPOT_ACCESS_TOKEN"):
        return ""

    try:
        deals = search_deals(limit=15)
        contacts = search_contacts_recent(limit=10, days=7)
    except Exception as e:
        return f"HubSpot API error: {e}\n\n"

    # Filter out closed deals
    open_deals = [
        d for d in deals
        if d.get("properties", {}).get("dealstage", "").lower().find("closed") < 0
    ]

    lines: list[str] = []

    # --- Pipeline ---
    lines.append("## HubSpot Pipeline (from CRM)")
    if not open_deals:
        lines.append("No open deals in HubSpot.")
    else:
        for d in open_deals[:10]:
            props = d.get("properties", {})
            name = props.get("dealname", "Unnamed")
            stage = _stage_label(props.get("dealstage"))
            amount = props.get("amount", "")
            last_mod = _format_date(props.get("hs_lastmodifieddate"))
            amt_str = f" ${amount}" if amount else ""
            lines.append(f"- **{name}** — {stage}{amt_str} (last updated {last_mod})")
    lines.append("")

    # --- Recent contacts ---
    lines.append("## Recent HubSpot Contacts (last 7 days)")
    if not contacts:
        lines.append("No contacts modified in the last 7 days.")
    else:
        for c in contacts[:5]:
            props = c.get("properties", {})
            email = props.get("email", "")
            first = props.get("firstname", "")
            last = props.get("lastname", "")
            company = props.get("company", "")
            name = f"{first} {last}".strip() or email or "Unknown"
            co = f" @ {company}" if company else ""
            lines.append(f"- {name}{co} — {email}")
    lines.append("")

    return "\n".join(lines)
