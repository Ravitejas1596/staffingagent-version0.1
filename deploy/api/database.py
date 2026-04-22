"""Async database engine and tenant-aware session factory.

Every request gets a database session with RLS enforced via:
    SET LOCAL app.tenant_id = '<uuid>'
This means even if application code forgets a WHERE clause,
PostgreSQL RLS blocks cross-tenant data access.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text

from platform.api.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_tenant_session(tenant_id: str) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session with RLS scoped to *tenant_id*."""
    async with async_session_factory() as session:
        await session.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant_id})
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
