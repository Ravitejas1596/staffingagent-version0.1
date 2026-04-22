"""
API gateway: abstraction layer decoupling agents from nBrain and Bullhorn.
Agents call this module instead of external APIs directly so deployment can swap backends.
"""
from __future__ import annotations

import asyncio
import json as jsonlib
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_TIMEOUT_SECONDS = 20.0
BTE_LINK_DEFAULT_TTL_DAYS = 7


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _get_required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise ValueError(f"{name} must be set")
    return value


def _extract_list_payload(
    payload: Any,
    *,
    preferred_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        ordered_keys: list[str] = []
        for key in preferred_keys or []:
            if key and key not in ordered_keys:
                ordered_keys.append(key)
        for key in ("results", "chunks", "documents", "data", "items"):
            if key not in ordered_keys:
                ordered_keys.append(key)
        for key in ordered_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _read_records_file(file_path: str) -> list[dict[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Records file not found: {file_path}")
    with path.open("r", encoding="utf-8") as f:
        payload = jsonlib.load(f)
    data = _extract_list_payload(payload)
    if not data:
        raise ValueError(f"Expected a JSON list of objects in {file_path}")
    return data


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "Cannot call sync loader while an event loop is running. "
        "Call the async gateway method directly."
    )


async def nbrain_query(tenant_id: str, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """
    Query nBrain knowledge base. Returns list of relevant chunks/documents.
    Requires NBRAIN_API_URL and NBRAIN_API_KEY in environment.
    """
    api_url = _get_required_env("NBRAIN_API_URL")
    api_key = _get_required_env("NBRAIN_API_KEY")
    endpoint = _join_url(api_url, os.getenv("NBRAIN_QUERY_PATH", "/query"))
    payload = {"tenant_id": tenant_id, "query": query, "limit": limit}
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = float(os.getenv("GATEWAY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    results_key = (os.getenv("NBRAIN_RESULTS_KEY") or "").strip()

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    return _extract_list_payload(body, preferred_keys=[results_key] if results_key else None)


async def _get_bullhorn_bearer_token(client: httpx.AsyncClient) -> str:
    static_token = (os.getenv("BULLHORN_BEARER_TOKEN") or "").strip()
    if static_token:
        return static_token

    token_url = (os.getenv("BULLHORN_TOKEN_URL") or "").strip()
    if not token_url:
        raise ValueError(
            "Set BULLHORN_BEARER_TOKEN or provide OAuth vars "
            "(BULLHORN_TOKEN_URL, BULLHORN_CLIENT_ID, BULLHORN_CLIENT_SECRET)"
        )
    client_id = _get_required_env("BULLHORN_CLIENT_ID")
    client_secret = _get_required_env("BULLHORN_CLIENT_SECRET")
    payload = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}

    response = await client.post(token_url, data=payload)
    response.raise_for_status()
    body = response.json()
    token = (body.get("access_token") or "").strip()
    if not token:
        raise ValueError("Bullhorn token response missing access_token")
    return token


async def bullhorn_rest(
    tenant_id: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Call Bullhorn REST API. Path is relative (for example: /entity/Placement/123).
    Uses either BULLHORN_BEARER_TOKEN or OAuth client credentials.
    """
    del tenant_id  # Tenant-specific credential routing is added in next phase.
    rest_url = _get_required_env("BULLHORN_REST_URL")
    timeout = float(os.getenv("GATEWAY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    async with httpx.AsyncClient(timeout=timeout) as client:
        token = await _get_bullhorn_bearer_token(client)
        response = await client.request(
            method=method.upper(),
            url=_join_url(rest_url, path),
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
    if isinstance(body, dict):
        return body
    return {"data": body}


def get_vms_records(tenant_id: str, source: str, **kwargs: Any) -> list[dict[str, Any]]:
    """
    Load VMS records for a tenant.
    Supported:
    - source='file' and file_path='path/to/records.json'
    """
    if source == "file":
        file_path = kwargs.get("file_path")
        if not file_path:
            raise ValueError("file_path is required when source='file'")
        return _read_records_file(str(file_path))
    raise NotImplementedError(
        f"Unsupported VMS source '{source}'. Add a source adapter in src/api/gateway.py."
    )


def get_ats_records(tenant_id: str, **kwargs: Any) -> list[dict[str, Any]]:
    """
    Load ATS/CRM records (for example Bullhorn placements/timesheets).
    Supported:
    - source='file' and file_path='path/to/records.json'
    - source='bullhorn' with path='/query/Placement' (optional params={...})
    """
    source = kwargs.get("source", "bullhorn")
    if source == "file":
        file_path = kwargs.get("file_path")
        if not file_path:
            raise ValueError("file_path is required when source='file'")
        return _read_records_file(str(file_path))

    if source == "bullhorn":
        path = kwargs.get("path", "/query/Placement")
        params = kwargs.get("params")
        results_key = str(kwargs.get("results_key") or os.getenv("ATS_RESULTS_KEY") or "").strip()
        payload = _run_async(
            bullhorn_rest(
                tenant_id=tenant_id,
                method="GET",
                path=str(path),
                params=params if isinstance(params, dict) else None,
            )
        )
        return _extract_list_payload(payload, preferred_keys=[results_key] if results_key else None)

    raise NotImplementedError(
        f"Unsupported ATS source '{source}'. Add a source adapter in src/api/gateway.py."
    )


# ─── Time Anomaly Agent — Bullhorn write methods ─────────────────────
# Reference: .cursor/plans/time_anomaly_v1_build.plan.md (Week 1 Day 2-3).
#
# These methods are intentionally stable in SIGNATURE but the Bullhorn REST
# paths are pending Josh's Apr 22 confirmation (marked TODO(josh, apr-22)
# at each call site). The agent code in src/agents/time_anomaly/ consumes
# these functions through the gateway per the project constitution — no
# agent node calls Bullhorn directly.


@dataclass(frozen=True)
class TimesheetCycle:
    """Placement-level timesheet cadence synced from Bullhorn.

    ``frequency`` is one of 'weekly', 'biweekly', 'semimonthly', 'monthly'.
    ``anchor_day`` is the lowercase day-of-week the cycle rolls over
    (e.g. 'sunday' for a Sunday-ending weekly cycle).
    """

    placement_id: str
    frequency: str
    anchor_day: str | None
    source: str  # 'bullhorn' | 'cached' | 'default'


@dataclass(frozen=True)
class BTELink:
    """Signed URL scoping an employee to a specific placement + pay period."""

    url: str
    expires_at: datetime
    candidate_id: str
    placement_id: str
    pay_period_end: date


@dataclass(frozen=True)
class WriteResult:
    """Common return shape for Bullhorn state-changing operations.

    ``prior_state`` is the snapshot that must be stored on the agent event
    (``agent_alert_events.prior_state_snapshot``) to power undo. Every write
    that mutates a timesheet or billable charge populates this so the 7-day
    reversal window has real data to restore.
    """

    entity_type: str
    entity_id: str
    prior_state: dict[str, Any]
    new_state: dict[str, Any]


async def get_placement_timesheet_cycle(
    tenant_id: str, placement_id: str
) -> TimesheetCycle:
    """Return the timesheet-cycle metadata for a placement.

    TODO(josh, apr-22): confirm the Bullhorn field name carrying the
    timesheet cycle on Placement. Expected candidates based on Cortney's
    spec walkthrough:

        * customTextN (bespoke per client)
        * payFrequency / timeExpenseFrequency (native enumeration)

    Until Josh confirms the authoritative field, this function raises
    NotImplementedError so detection surfaces a clear blocker rather than
    silently running against the wrong field.
    """
    del tenant_id, placement_id
    raise NotImplementedError(
        "get_placement_timesheet_cycle is blocked on Josh's Apr 22 "
        "confirmation of the Bullhorn timesheet-cycle field name. "
        "See .cursor/plans/time_anomaly_v1_build.plan.md §Pre-sprint dependencies."
    )


async def get_timesheet_by_placement_and_period(
    tenant_id: str,
    placement_id: str,
    pay_period_start: date,
    pay_period_end: date,
) -> dict[str, Any] | None:
    """Look up a timesheet for a placement within a pay period.

    Returns the raw Bullhorn timesheet dict, or ``None`` when no timesheet
    has been entered yet. The Detect stage of the Time Anomaly agent uses
    this to distinguish "no timesheet" (fire Group A1) from "timesheet
    entered" (quiet path).
    """
    # TODO(josh, apr-22): confirm Bullhorn Timesheet query shape. Likely:
    #   /query/Timesheet?where=placementId=<pid> AND weekEnding>=<start>
    #                         AND weekEnding<=<end>&fields=id,status,...
    path = "/query/Timesheet"
    where_clause = (
        f"placement.id={placement_id}"
        f" AND weekEnding>='{pay_period_start.isoformat()}'"
        f" AND weekEnding<='{pay_period_end.isoformat()}'"
    )
    params = {
        "where": where_clause,
        "fields": "id,status,weekEnding,regularHours,overtimeHours,totalHours",
    }
    payload = await bullhorn_rest(
        tenant_id=tenant_id,
        method="GET",
        path=path,
        params=params,
    )
    rows = _extract_list_payload(payload, preferred_keys=["data"])
    return rows[0] if rows else None


async def generate_bte_timesheet_link(
    tenant_id: str,
    candidate_id: str,
    placement_id: str,
    pay_period_end: date,
    *,
    ttl_days: int = BTE_LINK_DEFAULT_TTL_DAYS,
) -> BTELink:
    """Generate a signed Bullhorn Time & Expense link for an employee.

    TODO(josh, apr-22): confirm BTE signed-URL endpoint shape. Two likely
    paths per Cortney's spec:

        POST /bte/signed-url  (JSON body with candidateId, placementId,
                               payPeriodEnd, ttlDays)
        POST /time-expense/links  (legacy)

    The signed URL must scope the employee to the specific placement and
    pay period so arriving at the BTE page pre-populates correctly. TTL
    defaults to 7 days so a reminder sent on Monday still works on Friday.
    """
    del tenant_id, candidate_id, placement_id, pay_period_end, ttl_days
    raise NotImplementedError(
        "generate_bte_timesheet_link is blocked on Josh's Apr 22 "
        "confirmation of the BTE signed-URL endpoint. "
        "See .cursor/plans/time_anomaly_v1_build.plan.md §Pre-sprint dependencies."
    )


async def mark_timesheet_dnw(
    tenant_id: str,
    timesheet_id: str,
    *,
    reason: str,
    actor_id: str,
) -> WriteResult:
    """Mark a timesheet as Did-Not-Work on the employee's behalf.

    ``prior_state`` on the returned :class:`WriteResult` carries the fields
    the reversal path needs: previous status, regular/OT hours, comments.
    The agent writes this dict into ``agent_alert_events.prior_state_snapshot``
    so an HITL "Undo DNW" action within 7 days can call
    :func:`reverse_timesheet_dnw` to restore the original values.
    """
    # TODO(josh, apr-22): confirm BTE DNW endpoint. Likely:
    #   PATCH /entity/Timesheet/<id> { status: 'DidNotWork', note: <reason> }
    # Uses BTE service account credentials (separate from tenant Bullhorn
    # creds) per the build plan's handoff items.
    fields = "id,status,regularHours,overtimeHours,totalHours,comments"
    current = await bullhorn_rest(
        tenant_id=tenant_id,
        method="GET",
        path=f"/entity/Timesheet/{timesheet_id}",
        params={"fields": fields},
    )
    prior_state = _extract_entity_data(current)

    updated = await bullhorn_rest(
        tenant_id=tenant_id,
        method="POST",
        path=f"/entity/Timesheet/{timesheet_id}",
        json={
            "status": "DidNotWork",
            "comments": f"[StaffingAgent DNW] {reason} (actor={actor_id})",
        },
    )
    return WriteResult(
        entity_type="Timesheet",
        entity_id=str(timesheet_id),
        prior_state=prior_state,
        new_state=_extract_entity_data(updated),
    )


async def set_billable_charge_hold(
    tenant_id: str,
    charge_id: str,
    *,
    reason: str,
) -> WriteResult:
    """Place a Bullhorn billable charge on hold pending review.

    Used by Group B (hours-over-limit) and Group C (variance) to stop a
    questionable charge from flowing into invoicing while the anomaly is
    resolved. Reversal is :func:`release_billable_charge_hold`.
    """
    # TODO(josh, apr-22): confirm Bullhorn BillableCharge hold field name.
    # Typical candidates: 'isOnHold', 'holdStatus', customBool5, etc.
    fields = "id,status,statusReason,isOnHold,holdReason"
    current = await bullhorn_rest(
        tenant_id=tenant_id,
        method="GET",
        path=f"/entity/BillableCharge/{charge_id}",
        params={"fields": fields},
    )
    prior_state = _extract_entity_data(current)
    updated = await bullhorn_rest(
        tenant_id=tenant_id,
        method="POST",
        path=f"/entity/BillableCharge/{charge_id}",
        json={
            "isOnHold": True,
            "holdReason": reason,
        },
    )
    return WriteResult(
        entity_type="BillableCharge",
        entity_id=str(charge_id),
        prior_state=prior_state,
        new_state=_extract_entity_data(updated),
    )


async def release_billable_charge_hold(
    tenant_id: str, charge_id: str
) -> WriteResult:
    """Reverse :func:`set_billable_charge_hold`. Restores ``isOnHold=False``."""
    fields = "id,status,statusReason,isOnHold,holdReason"
    current = await bullhorn_rest(
        tenant_id=tenant_id,
        method="GET",
        path=f"/entity/BillableCharge/{charge_id}",
        params={"fields": fields},
    )
    prior_state = _extract_entity_data(current)
    updated = await bullhorn_rest(
        tenant_id=tenant_id,
        method="POST",
        path=f"/entity/BillableCharge/{charge_id}",
        json={
            "isOnHold": False,
            "holdReason": None,
        },
    )
    return WriteResult(
        entity_type="BillableCharge",
        entity_id=str(charge_id),
        prior_state=prior_state,
        new_state=_extract_entity_data(updated),
    )


async def reverse_timesheet_dnw(
    tenant_id: str,
    timesheet_id: str,
    prior_state: dict[str, Any],
) -> WriteResult:
    """Restore a timesheet marked DNW back to its prior state.

    Consumer is the HITL "Undo DNW" affordance. Caller passes the
    ``prior_state`` snapshot stored on the original agent event; this
    function writes those exact values back and returns the new state for
    the reversal-event row.
    """
    fields = "id,status,regularHours,overtimeHours,totalHours,comments"
    current = await bullhorn_rest(
        tenant_id=tenant_id,
        method="GET",
        path=f"/entity/Timesheet/{timesheet_id}",
        params={"fields": fields},
    )
    prior_before_reverse = _extract_entity_data(current)
    payload = {
        key: prior_state[key]
        for key in ("status", "regularHours", "overtimeHours", "totalHours", "comments")
        if key in prior_state
    }
    updated = await bullhorn_rest(
        tenant_id=tenant_id,
        method="POST",
        path=f"/entity/Timesheet/{timesheet_id}",
        json=payload,
    )
    return WriteResult(
        entity_type="Timesheet",
        entity_id=str(timesheet_id),
        prior_state=prior_before_reverse,
        new_state=_extract_entity_data(updated),
    )


def _extract_entity_data(payload: Any) -> dict[str, Any]:
    """Unwrap Bullhorn's ``{"data": {...}}`` entity envelope."""
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload
    return {}


def _utcnow() -> datetime:  # exported for tests
    return datetime.now(timezone.utc)
