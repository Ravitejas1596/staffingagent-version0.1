"""Async database engine and tenant-aware session factory.

Every request gets a database session with RLS enforced via:
    SET LOCAL app.tenant_id = '<uuid>'

Migration 041 enables RLS + a per-tenant policy on every tenant-scoped
table, so PostgreSQL blocks cross-tenant reads/writes even if application
code forgets a WHERE clause.

Super-admin cross-tenant operations use `get_platform_session`, which sets
`SET LOCAL app.bypass_rls = 'on'`. Only call that from endpoints gated by
`require_super_admin`.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text

from app_platform.api.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


def _coerce_tenant_uuid(tenant_id: str | uuid.UUID) -> str:
    """Validate that *tenant_id* parses as a UUID and return its canonical form.

    We interpolate this value into `SET LOCAL app.tenant_id = '<uuid>'` because
    PostgreSQL does not accept bound parameters for SET statements. Validating
    with `uuid.UUID()` guarantees no SQL metacharacters can reach the server.
    """
    if isinstance(tenant_id, uuid.UUID):
        return str(tenant_id)
    return str(uuid.UUID(str(tenant_id)))


@asynccontextmanager
async def get_tenant_session(tenant_id: str | uuid.UUID) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session with RLS scoped to *tenant_id*.

    Raises ValueError if tenant_id is not a valid UUID.
    """
    safe_tid = _coerce_tenant_uuid(tenant_id)
    async with async_session_factory() as session:
        await session.execute(text(f"SET LOCAL app.tenant_id = '{safe_tid}'"))
        await session.execute(text("SET LOCAL app.bypass_rls = 'off'"))
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_platform_session() -> AsyncGenerator[AsyncSession, None]:
    """Unscoped session for super_admin cross-tenant operations.

    Sets `app.bypass_rls = 'on'`, which the policies in migration 041 honor
    to return all rows regardless of tenant_id. Only use from endpoints
    gated behind require_super_admin.
    """
    async with async_session_factory() as session:
        await session.execute(text("SET LOCAL app.bypass_rls = 'on'"))
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
