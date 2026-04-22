"""Unit tests for the Jinja2-backed message template renderer.

The renderer's public contract has three guarantees this file pins down:

1. Tenant-scoped rows win over platform defaults.
2. Unknown variable names (either in ``variables=`` or in the template body)
   raise ``TemplateVariableError`` instead of silently rendering empty.
3. Missing / empty variable values raise ``TemplateVariableError`` so the
   agent never sends a message like "Your BTE link:  " with the link blank.

DB access is faked with an in-memory async session stub so these tests run
in CI without Postgres.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app_platform.api.message_templates import (
    TemplateNotFoundError,
    TemplateVariableError,
    render,
)


@dataclass
class _FakeTemplateRow:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    template_key: str
    channel: str
    language: str
    subject: str | None
    body: str
    active: bool = True


class _FakeScalars:
    def __init__(self, rows: list[_FakeTemplateRow]) -> None:
        self._rows = rows

    def all(self) -> list[_FakeTemplateRow]:
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows: list[_FakeTemplateRow]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeSession:
    """Minimal async-session stub honoring the ``execute().scalars().all()``
    path used by ``message_templates._fetch_template``."""

    def __init__(self, rows: list[_FakeTemplateRow]) -> None:
        self._rows = rows
        self.last_stmt: Any = None

    async def execute(self, stmt: Any) -> _FakeResult:
        self.last_stmt = stmt
        return _FakeResult(self._rows)


TENANT_ID = uuid.uuid4()


def _row(
    *,
    tenant_id: uuid.UUID | None,
    body: str,
    key: str = "time_anomaly.group_a1.sms",
) -> _FakeTemplateRow:
    return _FakeTemplateRow(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        template_key=key,
        channel="sms",
        language="en",
        subject=None,
        body=body,
    )


def _variables(**overrides: Any) -> dict[str, Any]:
    base = {
        "employee_first_name": "Avery",
        "week_ending_date": "2026-04-26",
        "bte_link": "https://bte.example/abc",
        "recruiter_name": "Cortney",
        "company_short_name": "StaffingAgent",
        "pay_period_start": "2026-04-20",
        "pay_period_end": "2026-04-26",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_platform_default_renders_when_no_tenant_override() -> None:
    session = _FakeSession([_row(tenant_id=None, body="Hi {{ employee_first_name }}")])
    result = await render(
        session,  # type: ignore[arg-type]
        template_key="time_anomaly.group_a1.sms",
        tenant_id=TENANT_ID,
        variables=_variables(),
    )
    assert result.body == "Hi Avery"
    assert result.source == "platform_default"


@pytest.mark.asyncio
async def test_tenant_override_wins_over_platform_default() -> None:
    session = _FakeSession(
        [
            _row(tenant_id=None, body="DEFAULT: Hi {{ employee_first_name }}"),
            _row(tenant_id=TENANT_ID, body="OVERRIDE: Hey {{ employee_first_name }}"),
        ]
    )
    result = await render(
        session,  # type: ignore[arg-type]
        template_key="time_anomaly.group_a1.sms",
        tenant_id=TENANT_ID,
        variables=_variables(),
    )
    assert result.body == "OVERRIDE: Hey Avery"
    assert result.source == "tenant_override"


@pytest.mark.asyncio
async def test_missing_template_raises_not_found() -> None:
    session = _FakeSession([])
    with pytest.raises(TemplateNotFoundError):
        await render(
            session,  # type: ignore[arg-type]
            template_key="time_anomaly.missing",
            tenant_id=TENANT_ID,
            variables=_variables(),
        )


@pytest.mark.asyncio
async def test_unknown_variable_in_input_rejected() -> None:
    session = _FakeSession([_row(tenant_id=None, body="hello {{ employee_first_name }}")])
    with pytest.raises(TemplateVariableError):
        await render(
            session,  # type: ignore[arg-type]
            template_key="time_anomaly.group_a1.sms",
            tenant_id=TENANT_ID,
            variables={**_variables(), "ssn": "123-45-6789"},
        )


@pytest.mark.asyncio
async def test_empty_variable_value_rejected() -> None:
    session = _FakeSession([_row(tenant_id=None, body="Your link: {{ bte_link }}")])
    with pytest.raises(TemplateVariableError):
        await render(
            session,  # type: ignore[arg-type]
            template_key="time_anomaly.group_a1.sms",
            tenant_id=TENANT_ID,
            variables=_variables(bte_link="   "),
        )


@pytest.mark.asyncio
async def test_template_referencing_undefined_variable_raises() -> None:
    # Body references {{ badge_number }} which is not in ALLOWED_VARIABLES.
    # StrictUndefined should surface this at render time even though the
    # caller-supplied variables dict is valid.
    session = _FakeSession(
        [_row(tenant_id=None, body="hi {{ employee_first_name }} ({{ badge_number }})")]
    )
    with pytest.raises(TemplateVariableError):
        await render(
            session,  # type: ignore[arg-type]
            template_key="time_anomaly.group_a1.sms",
            tenant_id=TENANT_ID,
            variables=_variables(),
        )


@pytest.mark.asyncio
async def test_tenant_none_selects_platform_default_only() -> None:
    session = _FakeSession([_row(tenant_id=None, body="Hi {{ employee_first_name }}")])
    result = await render(
        session,  # type: ignore[arg-type]
        template_key="time_anomaly.group_a1.sms",
        tenant_id=None,
        variables=_variables(),
    )
    assert result.source == "platform_default"
    assert result.body == "Hi Avery"
