"""SLA timer scheduling for the Time Anomaly agent.

The state machine pauses between ``outreach_sent`` and the follow-up
re-check. In production that pause is backed by an SQS delayed message:
the ``outreach_node`` enqueues a message with ``DelaySeconds`` set to
the first-reminder window (per severity), the worker
(``app_platform/workers/sla_timer_worker.py``) consumes it, and the
graph resumes.

SQS caps ``DelaySeconds`` at 900 (15 min). For SLA bands longer than
that we enqueue with the max delay and the worker re-schedules on
wakeup until the target ``scheduled_at`` is reached. That gives a
consistent envelope across severity bands without a separate
long-delay mechanism.

In tests / local dev the queue URL is unset and :func:`schedule_timer`
returns ``None`` — the caller falls through to the synchronous
in-memory path instead.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

SQS_MAX_DELAY_SECONDS = 900  # AWS hard limit for DelaySeconds
QUEUE_URL_ENV = "SLA_TIMER_QUEUE_URL"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _queue_url() -> str | None:
    val = (os.getenv(QUEUE_URL_ENV) or "").strip()
    return val or None


async def schedule_timer(
    *,
    alert_id: UUID,
    tenant_id: UUID,
    thread_id: str | None,
    reason: str,
    delay_seconds: int,
) -> str | None:
    """Enqueue an SLA timer message; return the SQS ``MessageId`` or ``None``.

    ``None`` means the queue isn't configured in this environment; the
    caller should fall through to the in-process wait_recheck path
    instead of silently dropping the timer.

    We dispatch boto3's sync SendMessage call via ``asyncio.to_thread``
    so the async agent nodes don't block the event loop on network IO.
    """
    queue_url = _queue_url()
    if not queue_url:
        return None

    scheduled_at = _now_utc() + timedelta(seconds=max(delay_seconds, 0))
    send_delay = min(max(delay_seconds, 0), SQS_MAX_DELAY_SECONDS)
    payload = {
        "alert_id": str(alert_id),
        "tenant_id": str(tenant_id),
        "thread_id": thread_id,
        "reason": reason,
        "scheduled_at": scheduled_at.isoformat(),
        "enqueued_at": _now_utc().isoformat(),
        "dedup_key": f"{alert_id}:{reason}:{uuid4().hex[:8]}",
    }

    try:
        message_id = await asyncio.to_thread(_send_sqs_message, queue_url, payload, send_delay)
    except Exception:
        logger.exception(
            "time_anomaly.schedule_timer.send_failed",
            extra={"alert_id": str(alert_id), "reason": reason},
        )
        return None
    logger.info(
        "time_anomaly.schedule_timer.enqueued",
        extra={
            "alert_id": str(alert_id),
            "reason": reason,
            "delay_seconds": send_delay,
            "scheduled_at": scheduled_at.isoformat(),
            "message_id": message_id,
        },
    )
    return message_id


def _send_sqs_message(queue_url: str, payload: dict[str, Any], delay_seconds: int) -> str:
    """Sync boto3 send. Kept isolated so the async caller can thread it."""
    import boto3  # local import: boto3 is a heavy dep; avoid at module load in tests

    sqs = boto3.client("sqs", region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    resp = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(payload),
        DelaySeconds=delay_seconds,
    )
    return str(resp.get("MessageId", ""))


def remaining_delay_seconds(scheduled_at_iso: str) -> int:
    """Return how many seconds from now until ``scheduled_at``.

    Used by the worker when it wakes from an intermediate SQS hop and
    needs to decide whether to re-enqueue (still more than 15 min left)
    or proceed with the wait_recheck (target has been reached).
    """
    try:
        scheduled_at = datetime.fromisoformat(scheduled_at_iso)
    except ValueError:
        return 0
    delta = (scheduled_at - _now_utc()).total_seconds()
    return max(int(delta), 0)
