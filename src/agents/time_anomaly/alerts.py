"""Alert lifecycle repository — the only place the Time Anomaly agent
touches ``agent_alerts`` and ``agent_alert_events``.

Nodes call into this module instead of writing SQL directly so (a) the
append-only invariant on ``agent_alert_events`` is honored in one place
and (b) every state transition emits a matching audit row without
relying on each node to remember.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import (
    AgentAlert,
    AgentAlertEvent,
    AuditLog,
)


@dataclass(frozen=True)
class CreatedAlert:
    alert_id: UUID
    tenant_id: UUID
    alert_type: str
    severity: str
    state: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_alert(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    agent_type: str,
    alert_type: str,
    severity: str,
    placement_id: UUID | None,
    candidate_id: UUID | None,
    pay_period_start: date | None,
    pay_period_end: date | None,
    trigger_context: dict[str, Any],
    langgraph_thread_id: str | None = None,
) -> CreatedAlert:
    """Insert a new ``agent_alerts`` row + matching ``detected`` event + audit."""
    alert = AgentAlert(
        tenant_id=tenant_id,
        agent_type=agent_type,
        alert_type=alert_type,
        severity=severity,
        state="detected",
        placement_id=placement_id,
        candidate_id=candidate_id,
        pay_period_start=pay_period_start,
        pay_period_end=pay_period_end,
        trigger_context=trigger_context,
        langgraph_thread_id=langgraph_thread_id,
        detected_at=_utcnow(),
    )
    session.add(alert)
    await session.flush()

    await _append_event(
        session,
        alert_id=alert.id,
        tenant_id=tenant_id,
        event_type="detected",
        actor_type="agent",
        actor_id="time_anomaly",
        metadata={"severity": severity, "alert_type": alert_type},
    )
    await _audit(
        session,
        tenant_id=tenant_id,
        agent_id="time_anomaly",
        action_type="detected",
        target_resource=f"alert:{alert.id}",
        metadata=trigger_context,
    )

    return CreatedAlert(
        alert_id=alert.id,
        tenant_id=tenant_id,
        alert_type=alert_type,
        severity=severity,
        state="detected",
    )


async def transition_state(
    session: AsyncSession,
    *,
    alert_id: UUID,
    new_state: str,
    resolution: str | None = None,
) -> None:
    """Update the alert's state with the matching timestamp column.

    ``resolution`` is required on the ``resolved`` transition and
    forbidden otherwise — enforced by the DB check constraint, but we
    check here too so callers get an immediate clean error.
    """
    if new_state == "resolved" and resolution is None:
        raise ValueError("resolved transition requires a resolution value")
    if new_state != "resolved" and resolution is not None:
        raise ValueError("resolution must be None unless transitioning to resolved")

    alert = await session.get(AgentAlert, alert_id)
    if alert is None:
        raise ValueError(f"agent_alerts row {alert_id} not found")

    alert.state = new_state
    now = _utcnow()
    if new_state == "outreach_sent":
        alert.outreach_sent_at = now
    elif new_state == "escalated_hitl":
        alert.escalated_at = now
    elif new_state == "resolved":
        alert.resolved_at = now
        alert.resolution = resolution

    await session.flush()


async def append_event(
    session: AsyncSession,
    *,
    alert_id: UUID,
    tenant_id: UUID,
    event_type: str,
    actor_type: str,
    actor_id: str,
    metadata: dict[str, Any] | None = None,
    reversal_available: bool = False,
    prior_state_snapshot: dict[str, Any] | None = None,
) -> UUID:
    """Public wrapper for appending an event + matching audit row."""
    event_id = await _append_event(
        session,
        alert_id=alert_id,
        tenant_id=tenant_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        metadata=metadata or {},
        reversal_available=reversal_available,
        prior_state_snapshot=prior_state_snapshot,
    )
    await _audit(
        session,
        tenant_id=tenant_id,
        agent_id="time_anomaly",
        action_type=event_type,
        target_resource=f"alert:{alert_id}",
        metadata=metadata or {},
    )
    return event_id


async def _append_event(
    session: AsyncSession,
    *,
    alert_id: UUID,
    tenant_id: UUID,
    event_type: str,
    actor_type: str,
    actor_id: str,
    metadata: dict[str, Any],
    reversal_available: bool = False,
    prior_state_snapshot: dict[str, Any] | None = None,
) -> UUID:
    """Raw event insert. No audit row — caller responsibility via append_event."""
    if reversal_available and prior_state_snapshot is None:
        raise ValueError(
            "reversal_available=True requires prior_state_snapshot to be populated"
        )
    event = AgentAlertEvent(
        id=uuid4(),
        alert_id=alert_id,
        tenant_id=tenant_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        reversal_available=reversal_available,
        prior_state_snapshot=prior_state_snapshot,
    )
    # AgentAlertEvent.metadata_ maps to DB column 'metadata'.
    event.metadata_ = metadata
    session.add(event)
    await session.flush()
    return event.id


async def _audit(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: str,
    action_type: str,
    target_resource: str,
    metadata: dict[str, Any],
) -> None:
    """Emit one AuditLog row mirroring the alert event."""
    row = AuditLog(
        tenant_id=tenant_id,
        agent_id=agent_id,
        action_type=action_type,
        target_resource=target_resource,
        output_summary=str(metadata)[:500],
    )
    session.add(row)
    await session.flush()
