"""Load per-tenant routing overrides from the ``agent_settings`` table.

When a tenant admin sets routing preferences (e.g. "use Claude for VMS
matching instead of Gemini"), those overrides are stored as rows in
``agent_settings`` with ``agent_type = '_global_'`` or the specific
agent type, and ``setting_key`` prefixed with ``routing.``.

Example rows::

    tenant_id | agent_type   | setting_key              | setting_value
    ----------+--------------+--------------------------+-------------
    ghr-uuid  | _global_     | routing.primary_provider | "anthropic"
    ghr-uuid  | vms_matching | routing.primary_provider | "gemini"
    ghr-uuid  | vms_matching | routing.primary_model    | "gemini-2.0-flash"

Agent-specific overrides win over ``_global_`` overrides.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import AgentSetting


async def load_routing_overrides(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    agent_type: str,
) -> dict[str, Any]:
    """Return merged routing overrides for a tenant + agent_type.

    Reads ``_global_`` routing keys first, then overlays agent-specific
    keys.  Returns a flat dict of ``{setting_key: setting_value}`` that
    the ``SmartRouter._resolve_route()`` method consumes.
    """
    stmt = (
        select(AgentSetting)
        .where(
            and_(
                AgentSetting.tenant_id == tenant_id,
                AgentSetting.agent_type.in_(["_global_", agent_type]),
                AgentSetting.setting_key.like("routing.%"),
            )
        )
        .order_by(AgentSetting.agent_type)  # _global_ sorts before others
    )
    rows = (await session.execute(stmt)).scalars().all()

    overrides: dict[str, Any] = {}
    for row in rows:
        # Agent-specific keys overwrite _global_ keys because they sort
        # after "_global_" alphabetically.
        overrides[row.setting_key] = row.setting_value

    return overrides
