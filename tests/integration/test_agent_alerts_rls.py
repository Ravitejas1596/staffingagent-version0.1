"""RLS + schema integrity tests for the Time Anomaly agent tables.

These tests talk to a real Postgres database because they exercise row-level
security policies and the append-only trigger on ``agent_alert_events``.

Set the ``TEST_DATABASE_URL`` environment variable to an empty Postgres
database where migrations 001-051 have been applied. The test will
``pytest.skip`` the module when the variable is missing so local unit runs
and CI paths without Postgres stay green.

Expected connection role: the URL's user must be (or be able to assume)
``app_user`` so RLS policies actually evaluate. If you're testing as a
superuser, set ``app.bypass_rls='off'`` and ``SET ROLE app_user`` before
running.

Reference: Time Anomaly build plan, Week 1 Day 1-2.
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
    reason="TEST_DATABASE_URL not set; skipping live-DB RLS tests.",
)


@pytest.fixture
async def conn() -> AsyncIterator["asyncpg.Connection"]:
    assert TEST_DATABASE_URL is not None
    connection = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        # Force evaluation under the app_user RLS policy, not superuser bypass.
        await connection.execute("SET LOCAL ROLE app_user")
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def two_tenants(conn: "asyncpg.Connection") -> tuple[uuid.UUID, uuid.UUID]:
    """Seed two tenants with unique slugs using bypass_rls, return their ids."""
    await conn.execute("SET LOCAL app.bypass_rls = 'on'")
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    slug_a = f"test-rls-a-{tenant_a.hex[:8]}"
    slug_b = f"test-rls-b-{tenant_b.hex[:8]}"
    await conn.execute(
        """
        INSERT INTO tenants (id, name, slug, tier, is_active)
        VALUES ($1, $2, $3, 'assess', TRUE),
               ($4, $5, $6, 'assess', TRUE)
        """,
        tenant_a, f"RLS Test A {tenant_a.hex[:8]}", slug_a,
        tenant_b, f"RLS Test B {tenant_b.hex[:8]}", slug_b,
    )
    yield tenant_a, tenant_b
    await conn.execute(
        "DELETE FROM tenants WHERE id = ANY($1::uuid[])",
        [tenant_a, tenant_b],
    )


async def _insert_alert(
    conn: "asyncpg.Connection",
    tenant_id: uuid.UUID,
    alert_type: str = "group_a1_first_miss",
) -> uuid.UUID:
    """Insert one agent_alerts row under bypass_rls. Returns the alert id."""
    alert_id = uuid.uuid4()
    await conn.execute("SET LOCAL app.bypass_rls = 'on'")
    await conn.execute(
        """
        INSERT INTO agent_alerts (
            id, tenant_id, agent_type, alert_type, severity, state,
            trigger_context, detected_at
        )
        VALUES ($1, $2, 'time_anomaly', $3, 'medium', 'detected',
                '{}'::jsonb, NOW())
        """,
        alert_id, tenant_id, alert_type,
    )
    return alert_id


class TestAgentAlertsRLS:
    async def test_tenant_a_cannot_read_tenant_b_alerts(
        self,
        conn: "asyncpg.Connection",
        two_tenants: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        tenant_a, tenant_b = two_tenants
        alert_a = await _insert_alert(conn, tenant_a)
        alert_b = await _insert_alert(conn, tenant_b)

        # Switch into tenant A's RLS context.
        await conn.execute("SET LOCAL app.bypass_rls = 'off'")
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_a}'")

        rows = await conn.fetch(
            "SELECT id FROM agent_alerts WHERE id = ANY($1::uuid[])",
            [alert_a, alert_b],
        )
        seen_ids = {r["id"] for r in rows}
        assert alert_a in seen_ids, "tenant A should see its own alert"
        assert alert_b not in seen_ids, "tenant A must not see tenant B's alert"

    async def test_tenant_a_cannot_insert_alert_for_tenant_b(
        self,
        conn: "asyncpg.Connection",
        two_tenants: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        tenant_a, tenant_b = two_tenants

        await conn.execute("SET LOCAL app.bypass_rls = 'off'")
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_a}'")

        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute(
                """
                INSERT INTO agent_alerts (
                    tenant_id, agent_type, alert_type, severity, state, trigger_context
                )
                VALUES ($1, 'time_anomaly', 'group_a1_first_miss', 'medium',
                        'detected', '{}'::jsonb)
                """,
                tenant_b,
            )

    async def test_alert_events_block_update(
        self,
        conn: "asyncpg.Connection",
        two_tenants: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        """The append-only trigger must reject UPDATE on agent_alert_events."""
        tenant_a, _ = two_tenants
        alert_id = await _insert_alert(conn, tenant_a)

        event_id = uuid.uuid4()
        await conn.execute("SET LOCAL app.bypass_rls = 'on'")
        await conn.execute(
            """
            INSERT INTO agent_alert_events (
                id, alert_id, tenant_id, event_type, actor_type, actor_id
            )
            VALUES ($1, $2, $3, 'detected', 'agent', 'agent')
            """,
            event_id, alert_id, tenant_a,
        )

        with pytest.raises(asyncpg.exceptions.PostgresError) as exc_info:
            await conn.execute(
                "UPDATE agent_alert_events SET actor_id = 'tampered' WHERE id = $1",
                event_id,
            )
        # The trigger raises SQLSTATE 23514 (check_violation) with our custom msg.
        assert "append-only" in str(exc_info.value).lower()


class TestExceptionRegistryRLS:
    async def test_tenant_isolation(
        self,
        conn: "asyncpg.Connection",
        two_tenants: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        tenant_a, tenant_b = two_tenants

        await conn.execute("SET LOCAL app.bypass_rls = 'on'")
        exc_a = uuid.uuid4()
        exc_b = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO exception_registry (
                exception_id, tenant_id, agent_id, alert_type, scope,
                entity_type, entity_id, created_by
            )
            VALUES ($1, $2, 'time_anomaly', 'group_c_variance', 'permanent',
                    'placement', 'bh-999', 'agent'),
                   ($3, $4, 'time_anomaly', 'group_c_variance', 'permanent',
                    'placement', 'bh-999', 'agent')
            """,
            exc_a, tenant_a, exc_b, tenant_b,
        )

        await conn.execute("SET LOCAL app.bypass_rls = 'off'")
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_a}'")

        rows = await conn.fetch(
            "SELECT exception_id FROM exception_registry WHERE exception_id = ANY($1::uuid[])",
            [exc_a, exc_b],
        )
        seen = {r["exception_id"] for r in rows}
        assert exc_a in seen
        assert exc_b not in seen


class TestMessageTemplatesRLS:
    async def test_platform_defaults_readable_by_every_tenant(
        self,
        conn: "asyncpg.Connection",
        two_tenants: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        """Seeded NULL-tenant_id templates (migration 050) must be visible to
        every tenant's read context. Tenant-scoped rows remain isolated."""
        tenant_a, _ = two_tenants

        await conn.execute("SET LOCAL app.bypass_rls = 'off'")
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_a}'")

        rows = await conn.fetch(
            """
            SELECT template_key FROM message_templates
            WHERE tenant_id IS NULL AND template_key LIKE 'time_anomaly.%'
            """
        )
        keys = {r["template_key"] for r in rows}
        # Migration 050 seeds at least the Group A1 SMS template.
        assert "time_anomaly.group_a1.sms" in keys
