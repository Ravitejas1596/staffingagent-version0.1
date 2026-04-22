"""HITL-facing endpoints for the agent_alerts lifecycle.

Mounted at ``/api/v1/alerts`` on the main FastAPI app. Three primary
routes:

- ``GET  /``                   — list alerts for the user's tenant (optionally
                                 filtered by state, agent, severity).
- ``POST /{alert_id}/resolve`` — human reviewer records a resolution.
  Optionally triggers a Bullhorn side-effect (mark_dnw, set_hold,
  release_hold) via the gateway; the side effect's ``prior_state`` is
  stored on the event so :func:`reverse` can undo it.
- ``POST /{alert_id}/reverse`` — 7-day undo window. Reads the most
  recent action event with ``reversal_available=True``, calls the
  matching gateway reversal method, and records a ``reversed`` event.

Rules:
- RLS is enforced by the session (``get_tenant_session`` sets
  ``app.tenant_id``), so we never need to filter ``tenant_id`` in the
  WHERE clauses.
- Every resolve/reverse appends an ``agent_alert_events`` row via the
  alert_repo so the audit trail stays append-only.
- Reversal is only allowed within ``REVERSAL_WINDOW_DAYS`` (7 days) of
  the original event's ``created_at``. Outside the window we 409.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.auth import TokenPayload, get_current_user
from app_platform.api.database import get_tenant_session
from app_platform.api.models import AgentAlert, AgentAlertEvent
from src.agents.time_anomaly import alerts as alert_repo
from src.api import gateway

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

REVERSAL_WINDOW_DAYS = 7
ACTIONABLE_EVENT_TYPES = {
    "timesheet_marked_dnw",
    "billable_charge_hold_set",
    "billable_charge_hold_released",
}


# ── response models ─────────────────────────────────────────────────


class AlertSummaryOut(BaseModel):
    id: UUID
    agent_type: str
    alert_type: str
    severity: str
    state: str
    detected_at: datetime
    outreach_sent_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None
    placement_id: Optional[UUID] = None
    pay_period_start: Optional[str] = None
    pay_period_end: Optional[str] = None
    trigger_context: dict[str, Any] = Field(default_factory=dict)


class AlertEventOut(BaseModel):
    id: UUID
    event_type: str
    actor_type: str
    actor_id: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    reversal_available: bool = False


class AlertDetailOut(AlertSummaryOut):
    events: list[AlertEventOut] = Field(default_factory=list)


class ResolveBody(BaseModel):
    resolution: str = Field(
        ..., description="e.g. employee_corrected, recruiter_override, exception_approved"
    )
    notes: Optional[str] = None
    action: Optional[str] = Field(
        None,
        description=(
            "Optional Bullhorn side-effect: 'mark_dnw', 'set_hold', "
            "'release_hold', or None to just transition state."
        ),
    )
    dry_run: bool = False


class ResolveOut(BaseModel):
    alert_id: UUID
    state: str
    resolution: str
    action_result: Optional[dict[str, Any]] = None


class ReverseBody(BaseModel):
    reason: str = Field(..., description="Why the human reviewer is reversing.")


class ReverseOut(BaseModel):
    alert_id: UUID
    state: str
    reversed_event_id: UUID
    action_result: dict[str, Any]


class AlertMetricsOut(BaseModel):
    """Rolling agent-performance KPIs for the Command Center dashboard card.

    All counts are for the requested window (default: 7 days). The
    ``auto_resolved_rate_pct`` is derived — it is the fraction of alerts
    triggered in the window that were closed with
    ``resolution='employee_corrected'`` without human intervention. This
    is the primary ROI number Chris surfaces to pilots: "x% of the
    things we caught resolved themselves before a human had to look."
    """

    window_days: int
    alerts_triggered: int
    hitl_required: int
    auto_resolved: int
    currently_open: int
    currently_hitl: int
    auto_resolved_rate_pct: float
    by_alert_type: dict[str, int] = Field(default_factory=dict)


# ── helpers ─────────────────────────────────────────────────────────


async def _load_alert(session: AsyncSession, alert_id: UUID) -> AgentAlert:
    row = await session.get(AgentAlert, alert_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"alert {alert_id} not found",
        )
    return row


async def _load_latest_actionable_event(
    session: AsyncSession, alert_id: UUID
) -> AgentAlertEvent | None:
    stmt = (
        select(AgentAlertEvent)
        .where(AgentAlertEvent.alert_id == alert_id)
        .where(AgentAlertEvent.reversal_available.is_(True))
        .order_by(desc(AgentAlertEvent.created_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _within_reversal_window(event: AgentAlertEvent) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=REVERSAL_WINDOW_DAYS)
    return event.created_at >= cutoff


# ── endpoints ───────────────────────────────────────────────────────


@router.get("/metrics", response_model=AlertMetricsOut)
async def alert_metrics(
    window_days: int = Query(7, ge=1, le=90),
    agent_type: Optional[str] = Query(
        "time_anomaly",
        description=(
            "Scope metrics to a single agent. Pass empty string to "
            "include all agents (future use)."
        ),
    ),
    current: TokenPayload = Depends(get_current_user),
) -> AlertMetricsOut:
    """Return rolling alert KPIs for the Command Center dashboard.

    Implementation detail: we run two queries against ``agent_alerts``:

    1. Windowed counts filtered by ``detected_at >= cutoff``. This is
       what powers *alerts_triggered / hitl_required / auto_resolved*
       and the per-``alert_type`` breakdown.
    2. A small "currently open / currently in HITL" tally that ignores
       the window — pilots want to know the *right now* backlog, not
       how many landed in the last 7 days.

    RLS means ``tenant_id`` is pinned by the session; no explicit filter
    needed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    async with get_tenant_session(current.tenant_id) as session:
        base_filter = [AgentAlert.detected_at >= cutoff]
        if agent_type:
            base_filter.append(AgentAlert.agent_type == agent_type)

        totals_stmt = select(
            func.count(AgentAlert.id).label("triggered"),
            func.coalesce(
                func.sum(
                    case(
                        (AgentAlert.escalated_at.is_not(None), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("hitl_required"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            AgentAlert.resolution == "employee_corrected",
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("auto_resolved"),
        ).where(*base_filter)
        totals = (await session.execute(totals_stmt)).one()

        breakdown_stmt = (
            select(AgentAlert.alert_type, func.count(AgentAlert.id))
            .where(*base_filter)
            .group_by(AgentAlert.alert_type)
        )
        breakdown_rows = (await session.execute(breakdown_stmt)).all()

        open_filter = [AgentAlert.state != "resolved"]
        if agent_type:
            open_filter.append(AgentAlert.agent_type == agent_type)
        open_stmt = select(
            func.count(AgentAlert.id).label("currently_open"),
            func.coalesce(
                func.sum(
                    case(
                        (AgentAlert.state == "escalated_hitl", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("currently_hitl"),
        ).where(*open_filter)
        open_totals = (await session.execute(open_stmt)).one()

    triggered = int(totals.triggered or 0)
    auto_resolved = int(totals.auto_resolved or 0)
    auto_rate = (auto_resolved / triggered * 100.0) if triggered else 0.0

    return AlertMetricsOut(
        window_days=window_days,
        alerts_triggered=triggered,
        hitl_required=int(totals.hitl_required or 0),
        auto_resolved=auto_resolved,
        currently_open=int(open_totals.currently_open or 0),
        currently_hitl=int(open_totals.currently_hitl or 0),
        auto_resolved_rate_pct=round(auto_rate, 1),
        by_alert_type={row[0]: int(row[1]) for row in breakdown_rows},
    )


@router.get("", response_model=list[AlertSummaryOut])
async def list_alerts(
    state_filter: Optional[str] = Query(
        None, alias="state", description="Filter by alert state."
    ),
    agent_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current: TokenPayload = Depends(get_current_user),
) -> list[AlertSummaryOut]:
    async with get_tenant_session(current.tenant_id) as session:
        stmt = select(AgentAlert).order_by(desc(AgentAlert.detected_at)).limit(limit)
        if state_filter:
            stmt = stmt.where(AgentAlert.state == state_filter)
        if agent_type:
            stmt = stmt.where(AgentAlert.agent_type == agent_type)
        if severity:
            stmt = stmt.where(AgentAlert.severity == severity)
        rows = (await session.execute(stmt)).scalars().all()
        return [_to_summary(r) for r in rows]


@router.get("/{alert_id}", response_model=AlertDetailOut)
async def get_alert(
    alert_id: UUID,
    current: TokenPayload = Depends(get_current_user),
) -> AlertDetailOut:
    async with get_tenant_session(current.tenant_id) as session:
        alert = await _load_alert(session, alert_id)
        events_stmt = (
            select(AgentAlertEvent)
            .where(AgentAlertEvent.alert_id == alert_id)
            .order_by(AgentAlertEvent.created_at.asc())
        )
        events = (await session.execute(events_stmt)).scalars().all()
        return AlertDetailOut(
            **_to_summary(alert).model_dump(),
            events=[_to_event_out(e) for e in events],
        )


@router.post(
    "/{alert_id}/resolve",
    response_model=ResolveOut,
    status_code=status.HTTP_200_OK,
)
async def resolve_alert(
    alert_id: UUID,
    body: ResolveBody,
    current: TokenPayload = Depends(get_current_user),
) -> ResolveOut:
    """Human reviewer closes an alert.

    If ``body.action`` is set, call the matching Bullhorn write method
    on the gateway BEFORE the state transition. The gateway returns a
    ``WriteResult`` with ``prior_state``; we persist that snapshot onto
    the event so the reverse endpoint can undo the change later.
    """
    # Block the trivially wrong resolution values early rather than
    # letting the CHECK constraint in Postgres raise an opaque 500.
    if not body.resolution.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="resolution is required",
        )

    async with get_tenant_session(current.tenant_id) as session:
        alert = await _load_alert(session, alert_id)
        if alert.state == "resolved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="alert is already resolved",
            )

        action_result: dict[str, Any] | None = None
        prior_snapshot: dict[str, Any] | None = None

        if body.action:
            action_result, prior_snapshot = await _run_gateway_action(
                tenant_id=current.tenant_id,
                actor_id=current.sub,
                alert=alert,
                action=body.action,
                dry_run=body.dry_run,
                notes=body.notes,
            )
            await alert_repo.append_event(
                session,
                alert_id=alert_id,
                tenant_id=UUID(current.tenant_id),
                event_type=_event_type_for(body.action),
                actor_type="human",
                actor_id=current.sub,
                metadata={
                    "action": body.action,
                    "notes": body.notes,
                    "dry_run": body.dry_run,
                    "result": action_result,
                },
                reversal_available=prior_snapshot is not None,
                prior_state_snapshot=prior_snapshot,
            )

        await alert_repo.append_event(
            session,
            alert_id=alert_id,
            tenant_id=UUID(current.tenant_id),
            event_type="resolved",
            actor_type="human",
            actor_id=current.sub,
            metadata={"resolution": body.resolution, "notes": body.notes},
        )
        await alert_repo.transition_state(
            session,
            alert_id=alert_id,
            new_state="resolved",
            resolution=body.resolution,
        )

    return ResolveOut(
        alert_id=alert_id,
        state="resolved",
        resolution=body.resolution,
        action_result=action_result,
    )


@router.post(
    "/{alert_id}/reverse",
    response_model=ReverseOut,
    status_code=status.HTTP_200_OK,
)
async def reverse_alert_action(
    alert_id: UUID,
    body: ReverseBody,
    current: TokenPayload = Depends(get_current_user),
) -> ReverseOut:
    """Undo the most recent reversible action on an alert.

    Looks up the latest ``agent_alert_events`` row with
    ``reversal_available=True`` and still inside the 7-day window.
    Calls the matching gateway reversal method and appends a
    ``reversed`` event; the prior_state_snapshot on the original event
    is used as the reversal payload (e.g. "charge was NOT on hold
    before we put it on hold").
    """
    async with get_tenant_session(current.tenant_id) as session:
        alert = await _load_alert(session, alert_id)
        latest = await _load_latest_actionable_event(session, alert_id)
        if latest is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="no reversible action on this alert",
            )
        if not _within_reversal_window(latest):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"reversal window ({REVERSAL_WINDOW_DAYS} days) has expired "
                    f"for this action"
                ),
            )

        action_result = await _run_gateway_reversal(
            tenant_id=current.tenant_id,
            alert=alert,
            original_event=latest,
        )
        reversal_event_id = await alert_repo.append_event(
            session,
            alert_id=alert_id,
            tenant_id=UUID(current.tenant_id),
            event_type="reversed",
            actor_type="human",
            actor_id=current.sub,
            metadata={
                "reason": body.reason,
                "reversed_event_id": str(latest.id),
                "result": action_result,
            },
        )

    return ReverseOut(
        alert_id=alert_id,
        state=alert.state,
        reversed_event_id=reversal_event_id,
        action_result=action_result,
    )


# ── gateway action dispatch ─────────────────────────────────────────


async def _run_gateway_action(
    *,
    tenant_id: str,
    actor_id: str,
    alert: AgentAlert,
    action: str,
    dry_run: bool,
    notes: Optional[str],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Dispatch to the correct Bullhorn gateway write method and return
    ``(action_result, prior_state_snapshot)``.

    The gateway takes concrete Bullhorn entity IDs (``timesheet_id`` /
    ``charge_id``). The HITL client hands us those IDs either explicitly
    on the request (for "apply to a different timesheet than the one we
    detected on" cases) or we look them up from the alert's trigger
    context and, as a fallback, from Bullhorn itself.

    In ``dry_run`` mode we SHORT-CIRCUIT the gateway call and return a
    synthetic result with no prior_state, so downstream code records
    the intent without mutating Bullhorn — useful for the first few
    days of pilot deployments while customers sanity-check behavior.
    """
    if dry_run:
        return (
            {"dry_run": True, "action": action, "entity_type": None, "new_state": {}},
            None,
        )

    timesheet_id = await _resolve_timesheet_id(tenant_id, alert)
    charge_id = await _resolve_charge_id(alert)
    reason = notes or f"staffingagent_{action}"

    if action == "mark_dnw":
        if not timesheet_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "mark_dnw requires a timesheet_id; no timesheet is "
                    "attached to this alert yet."
                ),
            )
        result = await gateway.mark_timesheet_dnw(
            tenant_id=tenant_id,
            timesheet_id=timesheet_id,
            reason=reason,
            actor_id=actor_id,
        )
    elif action == "set_hold":
        if not charge_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="set_hold requires a charge_id; none attached to alert.",
            )
        result = await gateway.set_billable_charge_hold(
            tenant_id=tenant_id,
            charge_id=charge_id,
            reason=reason,
        )
    elif action == "release_hold":
        if not charge_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="release_hold requires a charge_id; none attached to alert.",
            )
        result = await gateway.release_billable_charge_hold(
            tenant_id=tenant_id,
            charge_id=charge_id,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported action '{action}'",
        )
    return _write_result_dict(result), getattr(result, "prior_state", None)


async def _run_gateway_reversal(
    *,
    tenant_id: str,
    alert: AgentAlert,
    original_event: AgentAlertEvent,
) -> dict[str, Any]:
    action = (original_event.metadata_ or {}).get("action")
    original_result = (original_event.metadata_ or {}).get("result") or {}
    entity_id = original_result.get("entity_id") or ""

    if action == "mark_dnw":
        if not entity_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot reverse: original timesheet id missing from event",
            )
        result = await gateway.reverse_timesheet_dnw(
            tenant_id=tenant_id,
            timesheet_id=entity_id,
            prior_state=original_event.prior_state_snapshot or {},
        )
    elif action == "set_hold":
        if not entity_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot reverse: original charge id missing from event",
            )
        result = await gateway.release_billable_charge_hold(
            tenant_id=tenant_id,
            charge_id=entity_id,
        )
    elif action == "release_hold":
        if not entity_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot reverse: original charge id missing from event",
            )
        result = await gateway.set_billable_charge_hold(
            tenant_id=tenant_id,
            charge_id=entity_id,
            reason="reinstated_after_reversal",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"no reversal defined for action '{action}'",
        )
    return _write_result_dict(result)


async def _resolve_timesheet_id(tenant_id: str, alert: AgentAlert) -> str | None:
    """Prefer trigger_context; fall back to a fresh Bullhorn lookup."""
    ctx = alert.trigger_context or {}
    if ctx.get("timesheet_id"):
        return str(ctx["timesheet_id"])
    if not alert.pay_period_start or not alert.pay_period_end:
        return None
    bh_placement = _bh_placement_from_alert(alert)
    if not bh_placement:
        return None
    try:
        timesheet = await gateway.get_timesheet_by_placement_and_period(
            tenant_id=tenant_id,
            placement_id=bh_placement,
            pay_period_start=alert.pay_period_start,
            pay_period_end=alert.pay_period_end,
        )
    except Exception:
        logger.exception("alerts._resolve_timesheet_id.bullhorn_failed")
        return None
    return str(timesheet["id"]) if timesheet and timesheet.get("id") else None


async def _resolve_charge_id(alert: AgentAlert) -> str | None:
    """Charge lookups aren't on the gateway yet (lands with Josh's
    Billable Charge field confirmation). For now we require the HITL
    payload or the detector's trigger_context to carry it."""
    ctx = alert.trigger_context or {}
    charge = ctx.get("charge_id") or ctx.get("billable_charge_id")
    return str(charge) if charge else None


# ── serialization helpers ───────────────────────────────────────────


def _bh_placement_from_alert(alert: AgentAlert) -> str:
    """Placement table stores ``bullhorn_id``; AgentAlert holds only
    ``placement_id``. For action dispatch we look the value up lazily —
    but in practice outreach_node puts it into trigger_context, so we
    prefer that over a DB round-trip."""
    ctx = alert.trigger_context or {}
    return str(ctx.get("placement_bullhorn_id") or ctx.get("bullhorn_placement_id") or "")


def _event_type_for(action: str) -> str:
    return {
        "mark_dnw": "timesheet_marked_dnw",
        "set_hold": "billable_charge_hold_set",
        "release_hold": "billable_charge_hold_released",
    }.get(action, f"action_{action}")


def _write_result_dict(result: Any) -> dict[str, Any]:
    """``WriteResult`` may be a dataclass; fall back to ``__dict__``
    when ``model_dump`` isn't available."""
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "__dict__"):
        return dict(result.__dict__)
    return {"result": str(result)}


def _to_summary(alert: AgentAlert) -> AlertSummaryOut:
    return AlertSummaryOut(
        id=alert.id,
        agent_type=alert.agent_type,
        alert_type=alert.alert_type,
        severity=alert.severity,
        state=alert.state,
        detected_at=alert.detected_at,
        outreach_sent_at=alert.outreach_sent_at,
        escalated_at=alert.escalated_at,
        resolved_at=alert.resolved_at,
        resolution=alert.resolution,
        placement_id=alert.placement_id,
        pay_period_start=(
            alert.pay_period_start.isoformat() if alert.pay_period_start else None
        ),
        pay_period_end=(
            alert.pay_period_end.isoformat() if alert.pay_period_end else None
        ),
        trigger_context=alert.trigger_context or {},
    )


def _to_event_out(event: AgentAlertEvent) -> AlertEventOut:
    return AlertEventOut(
        id=event.id,
        event_type=event.event_type,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        created_at=event.created_at,
        metadata=event.metadata_ or {},
        reversal_available=bool(event.reversal_available),
    )
