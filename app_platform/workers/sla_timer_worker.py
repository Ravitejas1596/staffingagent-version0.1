"""SQS consumer that wakes the Time Anomaly agent after an SLA timer fires.

Message envelope (produced by :func:`src.agents.time_anomaly.timers.schedule_timer`):

    {
      "alert_id":     "<uuid>",
      "tenant_id":    "<uuid>",
      "thread_id":    "<langgraph thread id | null>",
      "reason":       "first_reminder" | "escalate",
      "scheduled_at": "<iso8601>",
      "enqueued_at":  "<iso8601>",
      "dedup_key":    "<alert_id>:<reason>:<short-hash>"
    }

Processing contract:

1. Poll SQS with long polling (20s).
2. If the ``scheduled_at`` target is still more than 15 minutes away
   (e.g. the original delay was truncated to the SQS 900s cap), re-enqueue
   with the remaining delay and delete the current message.
3. Otherwise call :func:`src.agents.time_anomaly.nodes.resume_alert` which
   re-polls Bullhorn, closes or escalates the alert, and — for
   ``first_reminder`` — enqueues the next (``escalate``) timer.
4. Delete the message on success; let SQS redrive to DLQ after 3 failures.

The worker is designed to be a plain ECS task with ``python -m
app_platform.workers.sla_timer_worker`` — no framework, no DB pool held
across iterations (each ``resume_alert`` opens its own tenant session),
no LangGraph instance cached (``resume_alert`` is a standalone coroutine
that does exactly what wait_recheck would have done).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


QUEUE_URL_ENV = "SLA_TIMER_QUEUE_URL"
POLL_WAIT_SECONDS = 20
POLL_MAX_MESSAGES = 10
SQS_MAX_DELAY_SECONDS = 900


class SLATimerWorker:
    """SQS consumer for Time Anomaly SLA timers."""

    def __init__(self, queue_url: str | None = None) -> None:
        self._queue_url = queue_url or (os.getenv(QUEUE_URL_ENV) or "").strip()
        if not self._queue_url:
            raise RuntimeError(
                f"{QUEUE_URL_ENV} must be set so the SLA timer worker "
                "knows which queue to poll."
            )
        self._shutdown = asyncio.Event()
        self._sqs = None  # lazy boto3 client

    # ── lifecycle ─────────────────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._shutdown.set)
            except NotImplementedError:
                pass

    def _client(self) -> Any:
        if self._sqs is None:
            import boto3

            self._sqs = boto3.client(
                "sqs", region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            )
        return self._sqs

    async def run(self) -> None:
        self._install_signal_handlers()
        logger.info(
            "sla_timer_worker.started", extra={"queue_url": self._queue_url}
        )
        while not self._shutdown.is_set():
            try:
                messages = await asyncio.to_thread(self._poll)
            except Exception:
                logger.exception("sla_timer_worker.poll_failed")
                await asyncio.sleep(5)
                continue

            if not messages:
                logger.debug("sla_timer_worker.idle")
                continue

            for message in messages:
                try:
                    handled = await self._process_message(message)
                except Exception:
                    logger.exception(
                        "sla_timer_worker.process_failed",
                        extra={"message_id": message.get("MessageId")},
                    )
                    continue
                if handled:
                    try:
                        await asyncio.to_thread(self._delete, message)
                    except Exception:
                        logger.exception("sla_timer_worker.delete_failed")

        logger.info("sla_timer_worker.stopped")

    # ── SQS IO ────────────────────────────────────────────────────

    def _poll(self) -> list[dict[str, Any]]:
        resp = self._client().receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=POLL_MAX_MESSAGES,
            WaitTimeSeconds=POLL_WAIT_SECONDS,
            MessageAttributeNames=["All"],
        )
        return resp.get("Messages", []) or []

    def _delete(self, message: dict[str, Any]) -> None:
        self._client().delete_message(
            QueueUrl=self._queue_url,
            ReceiptHandle=message["ReceiptHandle"],
        )

    def _enqueue_delayed(self, payload: dict[str, Any], delay_seconds: int) -> None:
        delay = max(0, min(delay_seconds, SQS_MAX_DELAY_SECONDS))
        self._client().send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps(payload),
            DelaySeconds=delay,
        )

    # ── message handling ──────────────────────────────────────────

    async def _process_message(self, message: dict[str, Any]) -> bool:
        """Return True if the message should be deleted, False to leave
        it in-flight for SQS to redrive (visibility timeout expires)."""
        body = message.get("Body") or "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error(
                "sla_timer_worker.malformed_payload",
                extra={"body": body[:500]},
            )
            return True  # drop malformed messages

        alert_id_raw = payload.get("alert_id")
        tenant_id_raw = payload.get("tenant_id")
        reason = payload.get("reason") or "first_reminder"
        if not alert_id_raw or not tenant_id_raw:
            logger.error(
                "sla_timer_worker.missing_ids", extra={"payload": payload}
            )
            return True

        # Bridge-delay handling: the original schedule may have wanted a
        # delay > 15 min, in which case the original send truncated to
        # the SQS max and we re-hop here until the target is reached.
        scheduled_at = payload.get("scheduled_at")
        if scheduled_at:
            from src.agents.time_anomaly.timers import remaining_delay_seconds

            remaining = remaining_delay_seconds(scheduled_at)
            if remaining > 60:  # still waiting
                logger.info(
                    "sla_timer_worker.rescheduling",
                    extra={
                        "alert_id": alert_id_raw,
                        "reason": reason,
                        "remaining_seconds": remaining,
                    },
                )
                await asyncio.to_thread(self._enqueue_delayed, payload, remaining)
                return True  # delete the current message

        try:
            alert_id = UUID(alert_id_raw)
            tenant_id = UUID(tenant_id_raw)
        except ValueError:
            logger.exception(
                "sla_timer_worker.bad_uuid", extra={"payload": payload}
            )
            return True

        # Import locally so the worker boot path doesn't pull langgraph.
        from src.agents.time_anomaly.nodes import resume_alert

        result = await resume_alert(
            alert_id=alert_id, tenant_id=tenant_id, reason=reason
        )
        logger.info(
            "sla_timer_worker.resumed",
            extra={
                "alert_id": alert_id_raw,
                "tenant_id": tenant_id_raw,
                "reason": reason,
                "status": result.get("status"),
            },
        )
        return True


async def amain() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker = SLATimerWorker()
    await worker.run()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
