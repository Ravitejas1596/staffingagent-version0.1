"""Integration tests for RLS enforcement.

These tests require a live PostgreSQL with migration 041 applied. They are
skipped unless DATABASE_ADMIN_URL is set (the admin connection is needed to
seed cross-tenant rows past RLS before testing the app_user path).

Run with:
    DATABASE_ADMIN_URL=... DATABASE_URL=... pytest tests/security/test_rls_integration.py
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_ADMIN_URL"),
    reason="integration test requires DATABASE_ADMIN_URL",
)


@pytest.mark.asyncio
async def test_cross_tenant_placements_blocked_by_rls() -> None:
    """A tenant-scoped session for tenant A must not see tenant B's rows,
    even when the application query has no WHERE tenant_id filter."""
    import asyncpg
    from sqlalchemy import text

    from app_platform.api.database import get_tenant_session

    admin_dsn = os.environ["DATABASE_ADMIN_URL"].replace("+asyncpg", "")
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(
            "INSERT INTO tenants (id, name, slug, tier) VALUES "
            "($1, 'A', $2, 'assess'), ($3, 'B', $4, 'assess')",
            tenant_a, f"a-{tenant_a}", tenant_b, f"b-{tenant_b}",
        )
        await admin.execute(
            "INSERT INTO placements (tenant_id, bullhorn_id, candidate_name) "
            "VALUES ($1, 'A-1', 'Alice'), ($2, 'B-1', 'Bob')",
            tenant_a, tenant_b,
        )

        async with get_tenant_session(str(tenant_a)) as session:
            rows = (await session.execute(
                text("SELECT candidate_name FROM placements")
            )).fetchall()
            names = {r[0] for r in rows}
            assert "Alice" in names, "tenant A should see its own row"
            assert "Bob" not in names, "RLS should hide tenant B's row"

        async with get_tenant_session(str(tenant_b)) as session:
            rows = (await session.execute(
                text("SELECT candidate_name FROM placements")
            )).fetchall()
            names = {r[0] for r in rows}
            assert "Bob" in names
            assert "Alice" not in names
    finally:
        await admin.execute("DELETE FROM placements WHERE tenant_id = ANY($1::uuid[])",
                            [tenant_a, tenant_b])
        await admin.execute("DELETE FROM tenants WHERE id = ANY($1::uuid[])",
                            [tenant_a, tenant_b])
        await admin.close()


@pytest.mark.asyncio
async def test_platform_session_bypasses_rls() -> None:
    """get_platform_session should see all tenants' rows."""
    import asyncpg
    from sqlalchemy import text

    from app_platform.api.database import get_platform_session

    admin_dsn = os.environ["DATABASE_ADMIN_URL"].replace("+asyncpg", "")
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(
            "INSERT INTO tenants (id, name, slug, tier) VALUES "
            "($1, 'A', $2, 'assess'), ($3, 'B', $4, 'assess')",
            tenant_a, f"a-{tenant_a}", tenant_b, f"b-{tenant_b}",
        )

        async with get_platform_session() as session:
            rows = (await session.execute(
                text("SELECT id FROM tenants WHERE id = ANY(:ids)").bindparams(
                    ids=[tenant_a, tenant_b]
                )
            )).fetchall()
            assert len(rows) == 2, "platform session should see both tenants"
    finally:
        await admin.execute("DELETE FROM tenants WHERE id = ANY($1::uuid[])",
                            [tenant_a, tenant_b])
        await admin.close()
