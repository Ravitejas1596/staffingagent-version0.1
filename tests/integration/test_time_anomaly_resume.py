"""End-to-end test for the Time Anomaly agent's resume_alert path.

Exercises the node-level contract that the SLA timer worker relies on
in production. Creates a seed ``agent_alert`` in ``outreach_sent`` state,
then calls :func:`src.agents.time_anomaly.nodes.resume_alert` with the
Bullhorn gateway patched so the test controls whether the timesheet is
"present" on re-poll.

Gated on ``TEST_DATABASE_URL`` just like the RLS tests — skips cleanly
when no live DB is configured.
"""
from __future__ import annotations

import os
import uuid
from typing import AsyncIterator

import pytest

asyncpg = pytest.importorskip("asyncpg")


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; skipping live-DB resume_alert test.",
)


@pytest.fixture
async def seeded() -> AsyncIterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Seed a tenant + placement + open alert. Yields (tenant_id,
    placement_id, alert_id) and tears them down after."""
    assert TEST_DATABASE_URL is not None
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    tenant_id = uuid.uuid4()
    placement_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    slug = f"test-ta-resume-{tenant_id.hex[:8]}"
    try:
        await conn.execute("SET LOCAL app.bypass_rls = 'on'")
        await conn.execute(
            """
            INSERT INTO tenants (id, name, slug, tier, is_active)
            VALUES ($1, $2, $3, 'assess', TRUE)
            """,
            tenant_id, f"TA Resume {tenant_id.hex[:8]}", slug,
        )
        await conn.execute(
            """
            INSERT INTO placements (id, tenant_id, bullhorn_id, status)
            VALUES ($1, $2, $3, 'active')
            """,
            placement_id, tenant_id, f"BH-{placement_id.hex[:8]}",
        )
        await conn.execute(
            """
            INSERT INTO agent_alerts (
                id, tenant_id, agent_type, alert_type, severity, state,
                placement_id, pay_period_start, pay_period_end,
                trigger_context, detected_at, outreach_sent_at
            )
            VALUES ($1, $2, 'time_anomaly', 'group_a1_first_miss',
                    'medium', 'outreach_sent', $3,
                    '2026-04-20', '2026-04-26',
                    '{}'::jsonb, NOW(), NOW())
            """,
            alert_id, tenant_id, placement_id,
        )
        yield tenant_id, placement_id, alert_id
    finally:
        await conn.execute("SET LOCAL app.bypass_rls = 'on'")
        await conn.execute(
            "DELETE FROM tenants WHERE id = $1", tenant_id
        )
        await conn.close()


@pytest.mark.asyncio
async def test_resume_closes_alert_when_timesheet_present(
    monkeypatch: pytest.MonkeyPatch,
    seeded: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, _placement, alert_id = seeded

    from src.agents.time_anomaly import nodes as agent_nodes
    from src.api import gateway

    async def _fake_timesheet(**_: object) -> dict[str, object]:
        return {"id": "TS-resume-test", "status": "Approved"}

    monkeypatch.setattr(gateway, "get_timesheet_by_placement_and_period", _fake_timesheet)

    result = await agent_nodes.resume_alert(
        alert_id=alert_id, tenant_id=tenant_id, reason="first_reminder"
    )
    assert result["status"] == "resolved"
    assert result["final_state"] == "resolved"

    # Confirm the row state actually moved in Postgres.
    assert TEST_DATABASE_URL is not None
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        await conn.execute("SET LOCAL app.bypass_rls = 'on'")
        row = await conn.fetchrow(
            "SELECT state, resolution FROM agent_alerts WHERE id = $1", alert_id
        )
        assert row["state"] == "resolved"
        assert row["resolution"] == "employee_corrected"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_resume_escalates_on_second_pass_without_timesheet(
    monkeypatch: pytest.MonkeyPatch,
    seeded: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, _placement, alert_id = seeded

    from src.agents.time_anomaly import nodes as agent_nodes
    from src.agents.time_anomaly import timers
    from src.api import gateway

    async def _no_timesheet(**_: object) -> None:
        return None

    monkeypatch.setattr(gateway, "get_timesheet_by_placement_and_period", _no_timesheet)

    async def _noop_timer(**_: object) -> None:
        return None

    monkeypatch.setattr(timers, "schedule_timer", _noop_timer)

    # First reminder pass → alert stays in outreach_sent (worker just
    # enqueues the escalation timer — our stubbed schedule_timer returns
    # None but the event + no-op branch still run).
    result_first = await agent_nodes.resume_alert(
        alert_id=alert_id, tenant_id=tenant_id, reason="first_reminder"
    )
    assert result_first["status"] == "waiting_for_escalation"

    # Escalation pass → alert transitions to escalated_hitl.
    result_second = await agent_nodes.resume_alert(
        alert_id=alert_id, tenant_id=tenant_id, reason="escalate"
    )
    assert result_second["status"] == "escalated"
    assert result_second["final_state"] == "escalated_hitl"

    assert TEST_DATABASE_URL is not None
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        await conn.execute("SET LOCAL app.bypass_rls = 'on'")
        row = await conn.fetchrow(
            "SELECT state, escalated_at FROM agent_alerts WHERE id = $1", alert_id
        )
        assert row["state"] == "escalated_hitl"
        assert row["escalated_at"] is not None

        events = await conn.fetch(
            "SELECT event_type FROM agent_alert_events WHERE alert_id = $1 ORDER BY created_at",
            alert_id,
        )
        event_types = [e["event_type"] for e in events]
        assert "first_reminder_sent" in event_types
        assert "hitl_assigned" in event_types
    finally:
        await conn.close()
