"""Unit tests for src/agents/time_anomaly/config.py.

Exercises the platform-default → tenant-override merge path so a tenant
admin can tune thresholds from agent_settings without touching code. The
tests use an in-memory session stub (no Postgres required) that mimics the
``session.execute(select(...))`` shape the ``load_config`` function uses.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from src.agents.time_anomaly.config import (
    AGENT_TYPE,
    TimeAnomalyConfig,
    load_config,
)


@dataclass
class _FakeSetting:
    """Mimics the columns ``load_config`` reads off AgentSetting."""

    tenant_id: uuid.UUID
    agent_type: str
    setting_key: str
    setting_value: Any


class _FakeScalars:
    def __init__(self, rows: list[_FakeSetting]) -> None:
        self._rows = rows

    def all(self) -> list[_FakeSetting]:
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows: list[_FakeSetting]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows: list[_FakeSetting]) -> None:
        self._rows = rows

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self._rows)


TENANT = uuid.uuid4()


@pytest.mark.asyncio
async def test_load_config_returns_platform_defaults_when_no_overrides() -> None:
    session = _FakeSession([])
    cfg = await load_config(session, tenant_id=TENANT)  # type: ignore[arg-type]
    assert isinstance(cfg, TimeAnomalyConfig)
    assert cfg.group_a.consecutive_miss_threshold == 2
    assert cfg.group_c.tolerance_pct == pytest.approx(0.25)
    assert cfg.group_b.reg_hours_limit == pytest.approx(40.0)
    assert cfg.dry_run is False


@pytest.mark.asyncio
async def test_load_config_applies_group_c_tolerance_override() -> None:
    session = _FakeSession(
        [
            _FakeSetting(
                tenant_id=TENANT,
                agent_type=AGENT_TYPE,
                setting_key="group_c.tolerance_pct",
                setting_value=0.4,
            )
        ]
    )
    cfg = await load_config(session, tenant_id=TENANT)  # type: ignore[arg-type]
    assert cfg.group_c.tolerance_pct == pytest.approx(0.4)
    # Other fields stay on the platform default.
    assert cfg.group_a.consecutive_miss_threshold == 2


@pytest.mark.asyncio
async def test_load_config_ignores_unknown_keys() -> None:
    """Unknown setting keys should not raise — a typoed admin setting
    must degrade silently to platform defaults, never break the agent."""
    session = _FakeSession(
        [
            _FakeSetting(
                tenant_id=TENANT,
                agent_type=AGENT_TYPE,
                setting_key="group_q.nonexistent",
                setting_value="whatever",
            )
        ]
    )
    cfg = await load_config(session, tenant_id=TENANT)  # type: ignore[arg-type]
    assert cfg.group_c.tolerance_pct == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_load_config_applies_multiple_overrides_in_order() -> None:
    session = _FakeSession(
        [
            _FakeSetting(
                tenant_id=TENANT,
                agent_type=AGENT_TYPE,
                setting_key="group_a.consecutive_miss_threshold",
                setting_value=3,
            ),
            _FakeSetting(
                tenant_id=TENANT,
                agent_type=AGENT_TYPE,
                setting_key="group_b.reg_hours_limit",
                setting_value=45.0,
            ),
            _FakeSetting(
                tenant_id=TENANT,
                agent_type=AGENT_TYPE,
                setting_key="group_c.basis",
                setting_value="placement_history",
            ),
        ]
    )
    cfg = await load_config(session, tenant_id=TENANT)  # type: ignore[arg-type]
    assert cfg.group_a.consecutive_miss_threshold == 3
    assert cfg.group_b.reg_hours_limit == pytest.approx(45.0)
    assert cfg.group_c.basis == "placement_history"


@pytest.mark.asyncio
async def test_load_config_drops_override_with_bad_type() -> None:
    """A non-numeric value for a numeric threshold must not corrupt the
    agent config — fall back to the platform default, log, move on."""
    session = _FakeSession(
        [
            _FakeSetting(
                tenant_id=TENANT,
                agent_type=AGENT_TYPE,
                setting_key="group_c.tolerance_pct",
                setting_value="not-a-number",
            )
        ]
    )
    cfg = await load_config(session, tenant_id=TENANT)  # type: ignore[arg-type]
    assert cfg.group_c.tolerance_pct == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_load_config_propagates_dry_run_flag() -> None:
    session = _FakeSession([])
    cfg = await load_config(session, tenant_id=TENANT, dry_run=True)  # type: ignore[arg-type]
    assert cfg.dry_run is True
