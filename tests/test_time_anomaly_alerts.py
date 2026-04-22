"""Unit tests for src/agents/time_anomaly/alerts.py.

The alert repository owns the append-only invariant for
``agent_alert_events`` and the one-place enforcement of state-transition
semantics (resolved requires a resolution, other transitions reject
one). These tests pin those invariants down with a minimal async-session
stub — no real DB required.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest

from app_platform.api import models
from src.agents.time_anomaly import alerts as alert_repo


TENANT = uuid.uuid4()
PLACEMENT = uuid.uuid4()


class _FakeSession:
    """Minimal stand-in for AsyncSession.

    Captures ``session.add`` calls so tests can assert which ORM objects
    were created, and supports ``session.get`` via a dict lookup. Only
    the methods the alerts repo actually uses are implemented.
    """

    def __init__(self, store: dict[tuple[type, uuid.UUID], Any] | None = None) -> None:
        self.added: list[Any] = []
        self._store = store or {}

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def get(self, model: type, pk: uuid.UUID) -> Any:
        return self._store.get((model, pk))

    async def execute(self, _stmt: Any) -> Any:  # pragma: no cover
        raise AssertionError("alert repo methods should not issue raw execute() calls")


def _alert_with_id(alert_id: uuid.UUID) -> models.AgentAlert:
    return models.AgentAlert(
        id=alert_id,
        tenant_id=TENANT,
        agent_type="time_anomaly",
        alert_type="group_a1_first_miss",
        severity="medium",
        state="outreach_sent",
    )


@pytest.mark.asyncio
async def test_create_alert_adds_alert_event_and_audit() -> None:
    session = _FakeSession()
    created = await alert_repo.create_alert(
        session,  # type: ignore[arg-type]
        tenant_id=TENANT,
        agent_type="time_anomaly",
        alert_type="group_a1_first_miss",
        severity="medium",
        placement_id=PLACEMENT,
        candidate_id=None,
        pay_period_start=date(2026, 4, 20),
        pay_period_end=date(2026, 4, 26),
        trigger_context={"reason": "first_miss_no_timesheet"},
    )
    kinds = [type(o).__name__ for o in session.added]
    assert kinds == ["AgentAlert", "AgentAlertEvent", "AuditLog"]
    assert created.alert_type == "group_a1_first_miss"
    assert created.severity == "medium"
    assert created.state == "detected"
    event = session.added[1]
    assert event.event_type == "detected"
    assert event.actor_type == "agent"
    assert event.metadata_["severity"] == "medium"


@pytest.mark.asyncio
async def test_transition_to_resolved_requires_resolution() -> None:
    alert_id = uuid.uuid4()
    session = _FakeSession({(models.AgentAlert, alert_id): _alert_with_id(alert_id)})
    with pytest.raises(ValueError, match="resolution"):
        await alert_repo.transition_state(
            session, alert_id=alert_id, new_state="resolved"  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_non_resolved_transition_rejects_resolution_arg() -> None:
    alert_id = uuid.uuid4()
    session = _FakeSession({(models.AgentAlert, alert_id): _alert_with_id(alert_id)})
    with pytest.raises(ValueError, match="resolution"):
        await alert_repo.transition_state(
            session,  # type: ignore[arg-type]
            alert_id=alert_id,
            new_state="escalated_hitl",
            resolution="hitl_resolved",
        )


@pytest.mark.asyncio
async def test_transition_resolved_sets_resolved_at_and_resolution() -> None:
    alert_id = uuid.uuid4()
    alert = _alert_with_id(alert_id)
    session = _FakeSession({(models.AgentAlert, alert_id): alert})
    await alert_repo.transition_state(
        session,  # type: ignore[arg-type]
        alert_id=alert_id,
        new_state="resolved",
        resolution="employee_corrected",
    )
    assert alert.state == "resolved"
    assert alert.resolution == "employee_corrected"
    assert alert.resolved_at is not None


@pytest.mark.asyncio
async def test_transition_escalated_sets_escalated_at() -> None:
    alert_id = uuid.uuid4()
    alert = _alert_with_id(alert_id)
    session = _FakeSession({(models.AgentAlert, alert_id): alert})
    await alert_repo.transition_state(
        session,  # type: ignore[arg-type]
        alert_id=alert_id,
        new_state="escalated_hitl",
    )
    assert alert.state == "escalated_hitl"
    assert alert.escalated_at is not None


@pytest.mark.asyncio
async def test_append_event_with_reversal_requires_prior_state() -> None:
    session = _FakeSession()
    with pytest.raises(ValueError, match="prior_state_snapshot"):
        await alert_repo.append_event(
            session,  # type: ignore[arg-type]
            alert_id=uuid.uuid4(),
            tenant_id=TENANT,
            event_type="marked_dnw",
            actor_type="agent",
            actor_id="time_anomaly",
            reversal_available=True,
            prior_state_snapshot=None,
        )


@pytest.mark.asyncio
async def test_append_event_happy_path_adds_event_and_audit() -> None:
    session = _FakeSession()
    await alert_repo.append_event(
        session,  # type: ignore[arg-type]
        alert_id=uuid.uuid4(),
        tenant_id=TENANT,
        event_type="sms_sent",
        actor_type="agent",
        actor_id="time_anomaly",
        metadata={"sms_sid": "SM123"},
    )
    kinds = [type(o).__name__ for o in session.added]
    assert kinds == ["AgentAlertEvent", "AuditLog"]
    event = session.added[0]
    assert event.event_type == "sms_sent"
    assert event.metadata_ == {"sms_sid": "SM123"}
    assert event.reversal_available is False
    assert event.prior_state_snapshot is None


@pytest.mark.asyncio
async def test_transition_raises_when_alert_missing() -> None:
    session = _FakeSession()
    with pytest.raises(ValueError, match="not found"):
        await alert_repo.transition_state(
            session,  # type: ignore[arg-type]
            alert_id=uuid.uuid4(),
            new_state="escalated_hitl",
        )
