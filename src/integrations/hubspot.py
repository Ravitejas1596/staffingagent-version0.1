"""
HubSpot API client for StaffingAgent.ai.
Handles contact creation/update, deal management, and form submissions.
Designed for Starter tier; social posting methods are stubbed for Pro upgrade.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

HUBSPOT_BASE = "https://api.hubapi.com"
FORMS_BASE = "https://api.hsforms.com"


def _get_token() -> str:
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
    if not token:
        raise ValueError(
            "HUBSPOT_ACCESS_TOKEN must be set. "
            "Create a private app in HubSpot > Settings > Integrations > Private Apps."
        )
    return token


def _get_portal_id() -> str:
    pid = os.environ.get("HUBSPOT_PORTAL_ID", "")
    if not pid:
        raise ValueError("HUBSPOT_PORTAL_ID must be set (e.g., 245521589)")
    return pid


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


# --------------- Contacts ---------------

def create_or_update_contact(
    email: str,
    first_name: str = "",
    last_name: str = "",
    company: str = "",
    custom_properties: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Create a contact or update if email already exists.
    Uses the CRM v3 contacts API.
    """
    properties: dict[str, str] = {"email": email}
    if first_name:
        properties["firstname"] = first_name
    if last_name:
        properties["lastname"] = last_name
    if company:
        properties["company"] = company
    if custom_properties:
        properties.update(custom_properties)

    payload = {"properties": properties}

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
            headers=_headers(),
            json=payload,
        )

        if resp.status_code == 409:
            existing_id = resp.json().get("message", "").split("Existing ID: ")[-1].strip()
            if existing_id.isdigit():
                return update_contact(existing_id, properties)
            raise RuntimeError(f"Contact conflict but could not parse ID: {resp.text}")

        resp.raise_for_status()
        return resp.json()


def update_contact(contact_id: str, properties: dict[str, str]) -> dict[str, Any]:
    with httpx.Client(timeout=15) as client:
        resp = client.patch(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}",
            headers=_headers(),
            json={"properties": properties},
        )
        resp.raise_for_status()
        return resp.json()


def get_contact_by_email(email: str) -> dict[str, Any] | None:
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search",
            headers=_headers(),
            json={
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "email",
                        "operator": "EQ",
                        "value": email,
                    }]
                }]
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None


# --------------- Deals ---------------

PIPELINE_STAGES = {
    "lead_in": "Lead In",
    "discovery_booked": "Discovery Call Booked",
    "discovery_complete": "Discovery Complete",
    "proposal_sent": "Proposal Sent",
    "negotiation": "Negotiation",
    "closed_won": "Closed Won",
    "closed_lost": "Closed Lost",
}


def create_deal(
    deal_name: str,
    stage: str = "lead_in",
    amount: float | None = None,
    contact_id: str | None = None,
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "dealname": deal_name,
        "dealstage": stage,
        "pipeline": "default",
    }
    if amount is not None:
        properties["amount"] = str(amount)

    payload: dict[str, Any] = {"properties": properties}
    if contact_id:
        payload["associations"] = [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
        }]

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/deals",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


def update_deal_stage(deal_id: str, stage: str) -> dict[str, Any]:
    with httpx.Client(timeout=15) as client:
        resp = client.patch(
            f"{HUBSPOT_BASE}/crm/v3/objects/deals/{deal_id}",
            headers=_headers(),
            json={"properties": {"dealstage": stage}},
        )
        resp.raise_for_status()
        return resp.json()


def search_deals(
    limit: int = 25,
    sort_by: str = "hs_lastmodifieddate",
    sort_direction: str = "DESCENDING",
) -> list[dict[str, Any]]:
    """
    Search deals via CRM Search API.
    Returns list of deal objects with dealname, amount, dealstage, hs_lastmodifieddate.
    Caller should filter out closed deals if needed (dealstage contains 'closed').
    """
    payload: dict[str, Any] = {
        "properties": ["dealname", "amount", "dealstage", "hs_lastmodifieddate", "closedate"],
        "limit": min(limit, 100),
        "sorts": [{"propertyName": sort_by, "direction": sort_direction}],
    }

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/deals/search",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])


def search_contacts_recent(limit: int = 10, days: int = 7) -> list[dict[str, Any]]:
    """
    Search contacts modified in the last N days.
    Returns list of contact objects with email, firstname, lastname, company, hs_lastmodifieddate.
    """
    from datetime import datetime, timedelta, timezone

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "hs_lastmodifieddate",
                "operator": "GTE",
                "value": since,
            }]
        }],
        "properties": ["email", "firstname", "lastname", "company", "hs_lastmodifieddate"],
        "limit": limit,
        "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "DESCENDING"}],
    }

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])


# --------------- Forms API (no auth required) ---------------

def submit_form(
    email: str,
    first_name: str = "",
    last_name: str = "",
    company: str = "",
    form_guid: str = "",
    extra_fields: dict[str, str] | None = None,
) -> bool:
    """
    Submit to HubSpot Forms API. This is a public endpoint (no auth token needed).
    Used by the website JavaScript for lead capture.
    """
    portal_id = _get_portal_id()
    guid = form_guid or os.environ.get("HUBSPOT_FORM_GUID", "")
    if not guid:
        raise ValueError("HUBSPOT_FORM_GUID must be set or passed as form_guid")

    fields = [{"name": "email", "value": email}]
    if first_name:
        fields.append({"name": "firstname", "value": first_name})
    if last_name:
        fields.append({"name": "lastname", "value": last_name})
    if company:
        fields.append({"name": "company", "value": company})
    if extra_fields:
        for k, v in extra_fields.items():
            fields.append({"name": k, "value": v})

    payload = {"fields": fields}

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{FORMS_BASE}/submissions/v3/integration/submit/{portal_id}/{guid}",
            json=payload,
        )
        return resp.status_code in (200, 204)


# --------------- Social (Pro tier — stubbed) ---------------

def schedule_social_post(
    channel: str,
    content: str,
    publish_at: str | None = None,
) -> dict[str, Any]:
    """
    Schedule a social media post via HubSpot API.
    Requires Marketing Hub Professional or Enterprise.
    """
    raise NotImplementedError(
        "Social posting API requires HubSpot Marketing Hub Professional ($800/mo). "
        "Currently on Starter — use the HubSpot UI to schedule posts, or upgrade "
        "when lead volume justifies it."
    )
