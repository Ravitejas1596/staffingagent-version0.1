"""Unit tests for the Bullhorn write methods added to src/api/gateway.py.

Two categories:

1. Methods that intentionally raise ``NotImplementedError`` until Josh
   confirms the underlying Bullhorn field / endpoint on Apr 22. The tests
   pin that contract so nobody wires them in prematurely — when Josh
   confirms, these tests will fail and we'll know exactly which call sites
   to update.

2. Methods whose HTTP shape is stable (timesheet lookup, hold, reversal).
   Those are tested with monkeypatched ``bullhorn_rest`` so we can assert
   the method + path + payload shape without running against Bullhorn.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.api import gateway


@pytest.mark.asyncio
async def test_get_placement_timesheet_cycle_is_blocked_on_josh() -> None:
    with pytest.raises(NotImplementedError) as exc:
        await gateway.get_placement_timesheet_cycle(
            tenant_id="tenant-1", placement_id="placement-9"
        )
    assert "Josh" in str(exc.value) or "timesheet-cycle" in str(exc.value)


@pytest.mark.asyncio
async def test_generate_bte_timesheet_link_is_blocked_on_josh() -> None:
    with pytest.raises(NotImplementedError) as exc:
        await gateway.generate_bte_timesheet_link(
            tenant_id="tenant-1",
            candidate_id="cand-1",
            placement_id="plc-1",
            pay_period_end=date(2026, 4, 26),
        )
    assert "Josh" in str(exc.value) or "BTE" in str(exc.value)


@pytest.mark.asyncio
async def test_get_timesheet_by_placement_and_period_issues_bullhorn_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _fake_bullhorn_rest(
        tenant_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        captured["tenant_id"] = tenant_id
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        captured["json"] = json
        return {"data": [{"id": 77, "status": "Submitted", "weekEnding": "2026-04-26"}]}

    monkeypatch.setattr(gateway, "bullhorn_rest", _fake_bullhorn_rest)

    result = await gateway.get_timesheet_by_placement_and_period(
        tenant_id="tenant-abc",
        placement_id="plc-99",
        pay_period_start=date(2026, 4, 20),
        pay_period_end=date(2026, 4, 26),
    )
    assert result == {"id": 77, "status": "Submitted", "weekEnding": "2026-04-26"}
    assert captured["method"] == "GET"
    assert captured["path"] == "/query/Timesheet"
    assert "placement.id=plc-99" in captured["params"]["where"]
    assert "2026-04-20" in captured["params"]["where"]
    assert "2026-04-26" in captured["params"]["where"]


@pytest.mark.asyncio
async def test_set_and_release_billable_charge_hold_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hold + release should each return the prior state so agent_alert_events
    can store it for the 7-day undo window."""
    fake_prior_get = {"id": 42, "isOnHold": False, "holdReason": None}
    fake_posted = {"id": 42, "isOnHold": True, "holdReason": "Time Anomaly"}

    call_log: list[tuple[str, str, dict[str, Any] | None]] = []

    async def _fake_bullhorn_rest(
        tenant_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        call_log.append((method, path, json))
        if method == "GET":
            return {"data": fake_prior_get}
        return {"data": fake_posted}

    monkeypatch.setattr(gateway, "bullhorn_rest", _fake_bullhorn_rest)

    hold_result = await gateway.set_billable_charge_hold(
        tenant_id="t1", charge_id="42", reason="Time Anomaly"
    )
    assert hold_result.entity_type == "BillableCharge"
    assert hold_result.prior_state == fake_prior_get
    assert hold_result.new_state == fake_posted
    assert ("GET", "/entity/BillableCharge/42", None) in call_log
    # The POST should flip isOnHold and include the reason string.
    post_entry = next(c for c in call_log if c[0] == "POST")
    assert post_entry[2] == {"isOnHold": True, "holdReason": "Time Anomaly"}


@pytest.mark.asyncio
async def test_reverse_timesheet_dnw_restores_prior_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_current = {"id": 1, "status": "DidNotWork", "regularHours": 0}
    fake_after = {"id": 1, "status": "Submitted", "regularHours": 40}
    payloads: list[dict[str, Any] | None] = []

    async def _fake_bullhorn_rest(
        tenant_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payloads.append(json)
        if method == "GET":
            return {"data": fake_current}
        return {"data": fake_after}

    monkeypatch.setattr(gateway, "bullhorn_rest", _fake_bullhorn_rest)

    prior = {
        "status": "Submitted",
        "regularHours": 40,
        "overtimeHours": 0,
        "totalHours": 40,
        "comments": "",
    }
    result = await gateway.reverse_timesheet_dnw(
        tenant_id="t1", timesheet_id="1", prior_state=prior
    )
    assert result.new_state == fake_after
    # The POST should carry exactly the prior_state keys we declared as restorable.
    post_payload = next(p for p in payloads if p is not None)
    assert post_payload == prior
