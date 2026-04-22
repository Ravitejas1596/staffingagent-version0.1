"""Unit tests for the SLA timer scheduler.

The real boto3 call is patched out with ``monkeypatch`` so these run in
a plain virtualenv without AWS credentials. We verify three guarantees:

- With no ``SLA_TIMER_QUEUE_URL`` set, ``schedule_timer`` returns ``None``
  so callers fall through to the in-process wait_recheck path.
- With the env var set, the payload shape matches the worker's
  expectations (alert_id, tenant_id, reason, scheduled_at, dedup_key).
- ``remaining_delay_seconds`` returns a non-negative integer delta.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.agents.time_anomaly import timers


TENANT = uuid.uuid4()
ALERT = uuid.uuid4()


@pytest.mark.asyncio
async def test_schedule_timer_returns_none_when_queue_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLA_TIMER_QUEUE_URL", raising=False)
    result = await timers.schedule_timer(
        alert_id=ALERT,
        tenant_id=TENANT,
        thread_id=None,
        reason="first_reminder",
        delay_seconds=3600,
    )
    assert result is None


@pytest.mark.asyncio
async def test_schedule_timer_sends_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLA_TIMER_QUEUE_URL", "https://sqs.test/fake-queue")
    captured: dict[str, Any] = {}

    def _fake_send(queue_url: str, payload: dict[str, Any], delay_seconds: int) -> str:
        captured["queue_url"] = queue_url
        captured["payload"] = payload
        captured["delay"] = delay_seconds
        return "msg-abc-123"

    monkeypatch.setattr(timers, "_send_sqs_message", _fake_send)

    result = await timers.schedule_timer(
        alert_id=ALERT,
        tenant_id=TENANT,
        thread_id="thread-xyz",
        reason="first_reminder",
        delay_seconds=4 * 3600,  # exceeds SQS 15-min cap → truncated
    )
    assert result == "msg-abc-123"
    assert captured["queue_url"] == "https://sqs.test/fake-queue"
    assert captured["delay"] == timers.SQS_MAX_DELAY_SECONDS
    payload = captured["payload"]
    assert payload["alert_id"] == str(ALERT)
    assert payload["tenant_id"] == str(TENANT)
    assert payload["thread_id"] == "thread-xyz"
    assert payload["reason"] == "first_reminder"
    assert "scheduled_at" in payload
    assert "dedup_key" in payload
    # Sanity: the payload round-trips through JSON cleanly, same as the
    # production send path does.
    assert json.loads(json.dumps(payload))["alert_id"] == str(ALERT)


@pytest.mark.asyncio
async def test_schedule_timer_returns_none_on_send_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLA_TIMER_QUEUE_URL", "https://sqs.test/fake-queue")

    def _fail(*_: Any, **__: Any) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(timers, "_send_sqs_message", _fail)

    result = await timers.schedule_timer(
        alert_id=ALERT,
        tenant_id=TENANT,
        thread_id=None,
        reason="escalate",
        delay_seconds=60,
    )
    assert result is None


def test_remaining_delay_in_future() -> None:
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    assert 500 < timers.remaining_delay_seconds(future) <= 600


def test_remaining_delay_in_past_clamped_to_zero() -> None:
    past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    assert timers.remaining_delay_seconds(past) == 0


def test_remaining_delay_garbage_input_returns_zero() -> None:
    assert timers.remaining_delay_seconds("not an iso string") == 0
