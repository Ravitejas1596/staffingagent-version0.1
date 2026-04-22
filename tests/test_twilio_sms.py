"""Unit tests for the Twilio outbound SMS client.

These tests monkeypatch ``httpx.AsyncClient`` so no real network calls are
made, and cover the three behaviors that matter for agent correctness:

1. Dry-run short-circuits the HTTP call and returns a synthetic SendResult
   whose ``dry_run`` flag is True.
2. Real send posts to Twilio's Messages endpoint with the expected form
   payload and basic-auth credentials.
3. A 4xx response surfaces as ``TwilioSendError`` with structured body
   instead of a generic exception.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.integrations.twilio_sms import (
    SendResult,
    TwilioConfigError,
    TwilioSendError,
    TwilioSMSClient,
    _redact_phone,
)


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._json = json_body
        self.text = str(json_body)

    def json(self) -> dict[str, Any]:
        return self._json


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.last_post_args: tuple[Any, ...] | None = None
        self.last_post_kwargs: dict[str, Any] | None = None

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        self.last_post_args = args
        self.last_post_kwargs = kwargs
        return self._response


@pytest.mark.asyncio
async def test_dry_run_skips_http_call(monkeypatch: pytest.MonkeyPatch) -> None:
    # If AsyncClient is accessed, raise loudly so an accidental network call fails.
    def _forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("dry_run must not construct httpx.AsyncClient")

    monkeypatch.setattr(httpx, "AsyncClient", _forbidden)

    client = TwilioSMSClient(account_sid="AC_TEST", auth_token="tok", dry_run=True)
    result = await client.send(
        to="+15125551234",
        body="Hi there",
        messaging_service_sid="MG_TEST",
    )
    assert isinstance(result, SendResult)
    assert result.dry_run is True
    assert result.status == "dry_run"
    assert result.messaging_service_sid == "MG_TEST"
    assert result.sid.startswith("SM_DRYRUN_")


@pytest.mark.asyncio
async def test_real_send_posts_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(_FakeResponse(201, {"sid": "SM_REAL_123", "status": "queued"}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: fake)

    client = TwilioSMSClient(account_sid="AC_TEST", auth_token="token", dry_run=False)
    result = await client.send(
        to="+15125551234",
        body="Your timesheet is missing.",
        messaging_service_sid="MG_ABCDE",
    )

    assert result.dry_run is False
    assert result.sid == "SM_REAL_123"
    assert result.status == "queued"

    # Verify we posted to the right endpoint with correct form + auth.
    assert fake.last_post_args is not None
    url = fake.last_post_args[0]
    assert url.endswith("/Accounts/AC_TEST/Messages.json")
    assert fake.last_post_kwargs is not None
    assert fake.last_post_kwargs["data"]["To"] == "+15125551234"
    assert fake.last_post_kwargs["data"]["MessagingServiceSid"] == "MG_ABCDE"
    assert fake.last_post_kwargs["auth"] == ("AC_TEST", "token")


@pytest.mark.asyncio
async def test_error_response_raises_twilio_send_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient(_FakeResponse(400, {"code": 21211, "message": "Invalid 'To'"}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: fake)

    client = TwilioSMSClient(account_sid="AC", auth_token="tok", dry_run=False)
    with pytest.raises(TwilioSendError) as excinfo:
        await client.send(to="+1", body="b", messaging_service_sid="MG")
    assert excinfo.value.status_code == 400
    assert "Invalid 'To'" in str(excinfo.value)


@pytest.mark.asyncio
async def test_missing_credentials_raise_config_error() -> None:
    client = TwilioSMSClient(account_sid="", auth_token="", dry_run=False)
    with pytest.raises(TwilioConfigError):
        await client.send(to="+15125551234", body="hi", messaging_service_sid="MG")


def test_redact_phone_keeps_last_four_digits_only() -> None:
    assert _redact_phone("+15125551234") == "*******1234"
    assert _redact_phone("5551234") == "***1234"
    # Fewer than 4 digits: fully masked.
    assert _redact_phone("12") == "****"


@pytest.mark.asyncio
async def test_empty_inputs_raise_value_error() -> None:
    client = TwilioSMSClient(account_sid="AC", auth_token="t", dry_run=True)
    with pytest.raises(ValueError):
        await client.send(to="", body="x", messaging_service_sid="MG")
    with pytest.raises(ValueError):
        await client.send(to="+1", body="", messaging_service_sid="MG")
    with pytest.raises(ValueError):
        await client.send(to="+1", body="x", messaging_service_sid="")
