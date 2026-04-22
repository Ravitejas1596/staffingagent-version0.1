"""Twilio outbound-SMS client for agent-driven notifications.

v1 scope (locked in the Time Anomaly build plan):

- Outbound-only. No webhook handling, no inbound SMS parsing. Employees
  self-service via the BTE link embedded in the message body; Bullhorn state
  changes are detected via polling in ``src/api/gateway.py``.
- Per-tenant A2P 10DLC messaging service. Each tenant registers its own brand
  with The Campaign Registry so SMS deliverability stays attributable to the
  correct staffing company.
- Dry-run mode. When enabled, the client logs the intended send and emits a
  synthetic success response without calling Twilio. Used by ``agent_runs``
  with ``dry_run=true`` during pilot data validation.

This module deliberately does NOT depend on the ``twilio`` SDK — ``httpx`` is
already a core dependency and the Twilio REST API is a thin basic-auth POST.
Staying off the SDK also keeps the dry-run path trivial to exercise in
unit tests without monkey-patching a large class hierarchy.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx


_TWILIO_API_ROOT = "https://api.twilio.com/2010-04-01"
_DEFAULT_TIMEOUT_SECONDS = 20.0

logger = logging.getLogger(__name__)


class TwilioConfigError(RuntimeError):
    """Raised when required Twilio credentials are missing at send time."""


class TwilioSendError(RuntimeError):
    """Raised when Twilio rejects a send with a non-2xx response."""

    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        super().__init__(f"Twilio send failed ({status_code}): {body.get('message') or body}")
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class SendResult:
    """Result of a send attempt. ``dry_run=True`` means no network call fired."""

    sid: str
    status: str
    dry_run: bool
    messaging_service_sid: str
    to: str


class TwilioSMSClient:
    """Thin async wrapper around Twilio's Messages resource.

    Construct once per process; the underlying ``httpx.AsyncClient`` is created
    lazily per call to keep the class cheap to instantiate in tests and dry
    runs.
    """

    def __init__(
        self,
        *,
        account_sid: str | None = None,
        auth_token: str | None = None,
        dry_run: bool | None = None,
        timeout_seconds: float | None = None,
        api_root: str = _TWILIO_API_ROOT,
    ) -> None:
        self._account_sid = account_sid or (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
        self._auth_token = auth_token or (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
        env_dry_run = (os.getenv("TWILIO_DRY_RUN") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self._dry_run = env_dry_run if dry_run is None else dry_run
        self._timeout = timeout_seconds or float(
            os.getenv("TWILIO_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS))
        )
        self._api_root = api_root.rstrip("/")

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def _assert_credentials(self) -> None:
        if not self._account_sid or not self._auth_token:
            raise TwilioConfigError(
                "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set to send "
                "real SMS (dry_run=False)."
            )

    async def send(
        self,
        *,
        to: str,
        body: str,
        messaging_service_sid: str,
    ) -> SendResult:
        """Send one SMS via a Messaging Service SID.

        ``messaging_service_sid`` is per-tenant (stored on ``tenants`` in
        migration 048). Using the Messaging Service — rather than a bare
        from-number — lets Twilio choose the best A2P-registered number for
        the destination carrier automatically.
        """
        to = to.strip()
        if not to:
            raise ValueError("Recipient phone number is empty.")
        if not messaging_service_sid:
            raise ValueError("messaging_service_sid is required.")
        if not body:
            raise ValueError("Message body is empty.")

        if self._dry_run:
            # Log with PII redaction (last 4 digits only).
            masked_to = _redact_phone(to)
            logger.info(
                "twilio.dry_run.send",
                extra={
                    "to": masked_to,
                    "messaging_service_sid": messaging_service_sid,
                    "body_len": len(body),
                },
            )
            return SendResult(
                sid="SM_DRYRUN_0000000000000000000000000000",
                status="dry_run",
                dry_run=True,
                messaging_service_sid=messaging_service_sid,
                to=to,
            )

        self._assert_credentials()
        url = f"{self._api_root}/Accounts/{self._account_sid}/Messages.json"
        data = {
            "To": to,
            "Body": body,
            "MessagingServiceSid": messaging_service_sid,
        }
        auth = (self._account_sid, self._auth_token)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, data=data, auth=auth)

        if response.status_code >= 400:
            try:
                body_json = response.json()
            except ValueError:
                body_json = {"raw": response.text}
            raise TwilioSendError(response.status_code, body_json)

        payload = response.json()
        return SendResult(
            sid=str(payload.get("sid", "")),
            status=str(payload.get("status", "queued")),
            dry_run=False,
            messaging_service_sid=messaging_service_sid,
            to=to,
        )


def _redact_phone(phone: str) -> str:
    """Mask everything except the last 4 digits for log output."""
    digits = [ch for ch in phone if ch.isdigit()]
    if len(digits) <= 4:
        return "****"
    return "*" * (len(digits) - 4) + "".join(digits[-4:])


def get_twilio_client(*, dry_run: bool | None = None) -> TwilioSMSClient:
    """Module-level factory used by agent code and tests."""
    return TwilioSMSClient(dry_run=dry_run)
