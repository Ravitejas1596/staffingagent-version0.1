"""Unit tests for the HITL alerts endpoints.

We patch ``get_tenant_session`` and the gateway functions rather than
standing up a live Postgres, so these run in a plain virtualenv with
only the ``api`` optional dependencies installed. The live-DB path is
covered separately in ``tests/integration/test_agent_alerts_rls.py``
and ``test_time_anomaly_resume.py``.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from fastapi import FastAPI

# Import the router module lazily so the patch on get_tenant_session
# takes effect on the module-level reference the endpoints actually use.
from app_platform.api import alerts as alerts_mod
from src.api import gateway


TENANT = uuid.uuid4()
USER = uuid.uuid4()


@dataclass
class _AlertRow:
    id: uuid.UUID
    tenant_id: uuid.UUID = TENANT
    agent_type: str = "time_anomaly"
    alert_type: str = "group_a1_first_miss"
    severity: str = "medium"
    state: str = "escalated_hitl"
    resolution: str | None = None
    placement_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None
    pay_period_start: date | None = date(2026, 4, 20)
    pay_period_end: date | None = date(2026, 4, 26)
    trigger_context: dict[str, Any] | None = None
    assigned_to: uuid.UUID | None = None
    langgraph_thread_id: str | None = None
    detected_at: datetime = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
    outreach_sent_at: datetime | None = None
    first_reminder_at: datetime | None = None
    escalated_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
    updated_at: datetime = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)


@dataclass
class _EventRow:
    id: uuid.UUID
    alert_id: uuid.UUID
    tenant_id: uuid.UUID = TENANT
    event_type: str = "timesheet_marked_dnw"
    actor_type: str = "human"
    actor_id: str = str(USER)
    metadata_: dict[str, Any] | None = None
    reversal_available: bool = True
    prior_state_snapshot: dict[str, Any] | None = None
    reverses_event_id: uuid.UUID | None = None
    created_at: datetime = datetime(2026, 4, 21, 10, 5, tzinfo=timezone.utc)


class _FakeSession:
    """Minimal async session that satisfies the endpoints' needs.

    Honors ``alert_by_id`` / ``event_by_id`` / ``latest_actionable`` maps
    set by the test, and captures ``transition_state`` calls so tests
    can assert on them.
    """

    def __init__(self) -> None:
        self.alerts: dict[uuid.UUID, _AlertRow] = {}
        self.events: list[_EventRow] = []
        self.calls: list[tuple[str, Any]] = []

    async def get(self, model: Any, key: uuid.UUID) -> Any:
        if model.__name__ == "AgentAlert":
            return self.alerts.get(key)
        return None

    async def execute(self, _stmt: Any) -> Any:
        # These tests only need the "most recent reversible event" and
        # the "events for an alert" queries. We don't introspect the
        # statement; we let the stub's configuration decide what to
        # return based on which call number we're on.
        self.calls.append(("execute", _stmt))
        if self._execute_queue:
            return _Result(self._execute_queue.pop(0))
        return _Result(self._last_execute_result)

    _last_execute_result: Any = None

    @property
    def _execute_queue(self) -> list[Any]:
        if not hasattr(self, "_queue"):
            self._queue: list[Any] = []
        return self._queue

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: Any) -> None:
        pass


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalars(self) -> Any:
        outer = self

        class _S:
            def first(self_inner) -> Any:  # noqa: N805
                return outer._value

            def all(self_inner) -> list[Any]:  # noqa: N805
                if outer._value is None:
                    return []
                return (
                    list(outer._value)
                    if isinstance(outer._value, list)
                    else [outer._value]
                )

        return _S()

    def scalar_one_or_none(self) -> Any:
        return self._value

    def first(self) -> Any:
        return self._value

    def one(self) -> Any:
        return self._value

    def all(self) -> list[Any]:
        if self._value is None:
            return []
        return (
            list(self._value)
            if isinstance(self._value, list)
            else [self._value]
        )


@pytest.fixture
def app_and_session(monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, _FakeSession]:
    session = _FakeSession()

    @asynccontextmanager
    async def _fake_session(_tenant_id: str):
        yield session

    monkeypatch.setattr(alerts_mod, "get_tenant_session", _fake_session)

    async def _fake_create(*, actor_type: str = "human", **_: Any) -> uuid.UUID:
        # Not used in these tests; alert_repo.create_alert is seed-only.
        return uuid.uuid4()

    async def _fake_transition(_session: Any, *, alert_id: uuid.UUID, new_state: str, resolution: str | None = None) -> None:
        alert = session.alerts.get(alert_id)
        if alert:
            alert.state = new_state
            alert.resolution = resolution
            if new_state == "resolved":
                alert.resolved_at = datetime.now(timezone.utc)

    async def _fake_append(
        _session: Any,
        *,
        alert_id: uuid.UUID,
        tenant_id: uuid.UUID,
        event_type: str,
        actor_type: str,
        actor_id: str,
        metadata: dict[str, Any] | None = None,
        reversal_available: bool = False,
        prior_state_snapshot: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        event_id = uuid.uuid4()
        session.events.append(
            _EventRow(
                id=event_id,
                alert_id=alert_id,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor_id,
                metadata_=metadata,
                reversal_available=reversal_available,
                prior_state_snapshot=prior_state_snapshot,
            )
        )
        return event_id

    monkeypatch.setattr(alerts_mod.alert_repo, "transition_state", _fake_transition)
    monkeypatch.setattr(alerts_mod.alert_repo, "append_event", _fake_append)

    async def _fake_user() -> alerts_mod.TokenPayload:
        return alerts_mod.TokenPayload(
            sub=str(USER), tenant_id=str(TENANT), role="admin"
        )

    app = FastAPI()
    app.include_router(alerts_mod.router)
    # Swap the dependency so tests don't need a real JWT.
    app.dependency_overrides[alerts_mod.get_current_user] = _fake_user
    return app, session


# ── resolve ──────────────────────────────────────────────────────────


def test_resolve_requires_non_empty_resolution(app_and_session: tuple[FastAPI, _FakeSession]) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    session.alerts[alert_id] = _AlertRow(id=alert_id)
    client = TestClient(app)
    r = client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"resolution": "   "})
    assert r.status_code == 400


def test_resolve_rejects_already_resolved(app_and_session: tuple[FastAPI, _FakeSession]) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    session.alerts[alert_id] = _AlertRow(id=alert_id, state="resolved")
    client = TestClient(app)
    r = client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        json={"resolution": "employee_corrected"},
    )
    assert r.status_code == 409


def test_resolve_without_action_transitions_state(
    app_and_session: tuple[FastAPI, _FakeSession],
) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    session.alerts[alert_id] = _AlertRow(id=alert_id)
    client = TestClient(app)
    r = client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        json={"resolution": "recruiter_override", "notes": "approved by manager"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "resolved"
    assert body["resolution"] == "recruiter_override"
    assert body["action_result"] is None
    # Exactly one event ("resolved") appended.
    event_types = [e.event_type for e in session.events]
    assert event_types == ["resolved"]


def test_resolve_dry_run_skips_gateway_call(
    app_and_session: tuple[FastAPI, _FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    session.alerts[alert_id] = _AlertRow(
        id=alert_id, trigger_context={"timesheet_id": "TS-9"}
    )

    called: dict[str, bool] = {"mark": False}

    async def _fail(**_: Any) -> Any:
        called["mark"] = True
        raise AssertionError("gateway must not be called in dry_run")

    monkeypatch.setattr(gateway, "mark_timesheet_dnw", _fail)

    client = TestClient(app)
    r = client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        json={
            "resolution": "exception_approved",
            "action": "mark_dnw",
            "dry_run": True,
        },
    )
    assert r.status_code == 200
    assert called["mark"] is False
    # The action event should still be recorded for audit purposes.
    event_types = [e.event_type for e in session.events]
    assert "timesheet_marked_dnw" in event_types
    assert "resolved" in event_types


def test_resolve_with_mark_dnw_calls_gateway_and_stores_prior(
    app_and_session: tuple[FastAPI, _FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    session.alerts[alert_id] = _AlertRow(
        id=alert_id, trigger_context={"timesheet_id": "TS-7"}
    )

    prior = {"status": "Submitted", "regularHours": 40}

    async def _mark(**kwargs: Any) -> gateway.WriteResult:
        assert kwargs["timesheet_id"] == "TS-7"
        assert kwargs["actor_id"] == str(USER)
        return gateway.WriteResult(
            entity_type="Timesheet",
            entity_id="TS-7",
            prior_state=prior,
            new_state={"status": "DidNotWork"},
        )

    monkeypatch.setattr(gateway, "mark_timesheet_dnw", _mark)

    client = TestClient(app)
    r = client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        json={
            "resolution": "exception_approved",
            "action": "mark_dnw",
            "notes": "employee confirmed did not work",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action_result"]["entity_id"] == "TS-7"

    # The action event should carry reversal_available=True + the prior snapshot.
    action_event = next(
        e for e in session.events if e.event_type == "timesheet_marked_dnw"
    )
    assert action_event.reversal_available is True
    assert action_event.prior_state_snapshot == prior


def test_resolve_with_missing_timesheet_id_returns_409(
    app_and_session: tuple[FastAPI, _FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    # No timesheet_id in trigger_context and gateway lookup returns None.
    session.alerts[alert_id] = _AlertRow(
        id=alert_id,
        trigger_context={"placement_bullhorn_id": "BH-1"},
    )

    async def _no_ts(**_: Any) -> None:
        return None

    monkeypatch.setattr(gateway, "get_timesheet_by_placement_and_period", _no_ts)

    client = TestClient(app)
    r = client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        json={"resolution": "exception_approved", "action": "mark_dnw"},
    )
    assert r.status_code == 409


# ── reverse ──────────────────────────────────────────────────────────


def test_reverse_409_when_no_reversible_event(
    app_and_session: tuple[FastAPI, _FakeSession],
) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    session.alerts[alert_id] = _AlertRow(id=alert_id)
    # _Result returns session._last_execute_result; leave it None so the
    # "latest reversible event" query returns nothing.
    session._last_execute_result = None
    client = TestClient(app)
    r = client.post(
        f"/api/v1/alerts/{alert_id}/reverse", json={"reason": "user hit undo"}
    )
    assert r.status_code == 409


def test_reverse_409_when_outside_window(
    app_and_session: tuple[FastAPI, _FakeSession],
) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    session.alerts[alert_id] = _AlertRow(id=alert_id)
    old_event = _EventRow(
        id=uuid.uuid4(),
        alert_id=alert_id,
        event_type="timesheet_marked_dnw",
        reversal_available=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        metadata_={"action": "mark_dnw", "result": {"entity_id": "TS-1"}},
        prior_state_snapshot={"status": "Submitted"},
    )
    session._last_execute_result = old_event
    client = TestClient(app)
    r = client.post(
        f"/api/v1/alerts/{alert_id}/reverse", json={"reason": "too late"}
    )
    assert r.status_code == 409
    assert "window" in r.json()["detail"].lower()


def test_reverse_mark_dnw_calls_reverse_gateway(
    app_and_session: tuple[FastAPI, _FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, session = app_and_session
    alert_id = uuid.uuid4()
    session.alerts[alert_id] = _AlertRow(id=alert_id)
    original = _EventRow(
        id=uuid.uuid4(),
        alert_id=alert_id,
        event_type="timesheet_marked_dnw",
        reversal_available=True,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        metadata_={"action": "mark_dnw", "result": {"entity_id": "TS-9"}},
        prior_state_snapshot={"status": "Submitted", "regularHours": 40},
    )
    session._last_execute_result = original

    captured: dict[str, Any] = {}

    async def _reverse(**kwargs: Any) -> gateway.WriteResult:
        captured.update(kwargs)
        return gateway.WriteResult(
            entity_type="Timesheet",
            entity_id="TS-9",
            prior_state={"status": "DidNotWork"},
            new_state={"status": "Submitted"},
        )

    monkeypatch.setattr(gateway, "reverse_timesheet_dnw", _reverse)

    client = TestClient(app)
    r = client.post(
        f"/api/v1/alerts/{alert_id}/reverse", json={"reason": "user hit undo"}
    )
    assert r.status_code == 200, r.text
    assert captured["timesheet_id"] == "TS-9"
    assert captured["prior_state"]["status"] == "Submitted"
    body = r.json()
    assert body["alert_id"] == str(alert_id)
    # reversal event appended
    types = [e.event_type for e in session.events]
    assert "reversed" in types


# ── metrics ──────────────────────────────────────────────────────────


class _MetricsRow:
    """Minimal stand-in for a SQLAlchemy aggregate Row."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


def test_metrics_returns_window_counts_and_rate(
    app_and_session: tuple[FastAPI, _FakeSession],
) -> None:
    """Three execute() calls happen: totals, breakdown, open totals."""
    app, session = app_and_session
    # Queue up the three aggregate results in order.
    totals = _MetricsRow(triggered=10, hitl_required=3, auto_resolved=6)
    breakdown = [
        ("group_a1_first_miss", 5),
        ("group_b_total_over_limit", 3),
        ("group_c_variance", 2),
    ]
    open_totals = _MetricsRow(currently_open=4, currently_hitl=2)
    session._queue = [totals, breakdown, open_totals]

    client = TestClient(app)
    r = client.get("/api/v1/alerts/metrics?window_days=7")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["window_days"] == 7
    assert body["alerts_triggered"] == 10
    assert body["hitl_required"] == 3
    assert body["auto_resolved"] == 6
    assert body["currently_open"] == 4
    assert body["currently_hitl"] == 2
    # 6 auto-resolved out of 10 triggered = 60.0%
    assert body["auto_resolved_rate_pct"] == 60.0
    assert body["by_alert_type"] == {
        "group_a1_first_miss": 5,
        "group_b_total_over_limit": 3,
        "group_c_variance": 2,
    }


def test_metrics_zero_triggered_reports_zero_rate(
    app_and_session: tuple[FastAPI, _FakeSession],
) -> None:
    app, session = app_and_session
    session._queue = [
        _MetricsRow(triggered=0, hitl_required=0, auto_resolved=0),
        [],
        _MetricsRow(currently_open=0, currently_hitl=0),
    ]
    client = TestClient(app)
    r = client.get("/api/v1/alerts/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["alerts_triggered"] == 0
    assert body["auto_resolved_rate_pct"] == 0.0
    assert body["by_alert_type"] == {}
