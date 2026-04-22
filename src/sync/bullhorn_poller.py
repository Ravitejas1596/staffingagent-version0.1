"""
Bullhorn Event Subscription poller — near-real-time sync.

Polls the Bullhorn Event Subscription API every POLL_INTERVAL_SECONDS and
publishes raw change events to SQS. The consumer (bullhorn_consumer.py)
reads from SQS, fetches full records, and upserts to Aurora.

The nightly batch sync (bullhorn_sync.py) continues to run as a safety net.

Usage:
    python -m src.sync.bullhorn_poller                    # uses STAFFINGAGENT_TENANT env
    python -m src.sync.bullhorn_poller --tenant default

Required env vars: BULLHORN_* (see bullhorn_auth.py), DATABASE_URL,
                   BULLHORN_EVENTS_QUEUE_URL, AWS_DEFAULT_REGION
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import os
from typing import Any

import asyncpg
import boto3
import httpx

from src.sync._db import parse_db_url
from src.sync.bullhorn_auth import BullhornSession, get_session, refresh_session

log = logging.getLogger("bullhorn_poller")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
MAX_EVENTS_PER_POLL = 500
QUEUE_URL = os.environ.get("BULLHORN_EVENTS_QUEUE_URL", "")

# All 12 entities confirmed accepted by Bullhorn for sa-default subscription
# (verified 2026-04-15 via Postman PUT /event/subscription/sa-default)
SUBSCRIBED_ENTITIES = [
    "Placement",
    "Candidate",
    "JobOrder",
    "Timesheet",
    "BillableCharge",
    "PayableCharge",
    "ClientCorporation",
    "InvoiceStatement",
    "BillMaster",
    "BillMasterTransaction",
    "PayMaster",
    "PayMasterTransaction",
]


# ---------------------------------------------------------------------------
# SQS
# ---------------------------------------------------------------------------

def _sqs_client() -> Any:
    return boto3.client("sqs", region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))


def publish_events(sqs: Any, tenant_id: str, events: list[dict]) -> None:
    """
    Send one SQS message containing the full batch of raw Bullhorn events.
    The consumer groups by entityType and processes accordingly.
    """
    if not QUEUE_URL:
        log.warning("[poller] BULLHORN_EVENTS_QUEUE_URL not set — skipping SQS publish")
        return

    payload = {
        "tenant_id": tenant_id,
        "events": events,
        "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    body = json.dumps(payload)

    # SQS max message size is 256 KB — split if needed
    if len(body.encode()) > 200_000:
        mid = len(events) // 2
        publish_events(sqs, tenant_id, events[:mid])
        publish_events(sqs, tenant_id, events[mid:])
        return

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=body,
        MessageAttributes={
            "tenant_id": {"DataType": "String", "StringValue": tenant_id},
            "event_count": {"DataType": "Number", "StringValue": str(len(events))},
        },
    )
    log.info("[poller] Published %d event(s) to SQS", len(events))


# ---------------------------------------------------------------------------
# Subscription management
# ---------------------------------------------------------------------------

def _subscription_id(tenant_slug: str) -> str:
    # Bullhorn subscription IDs must be ≤50 chars, alphanumeric + hyphens
    slug = tenant_slug[:30].replace("_", "-").lower()
    return f"sa-{slug}"


async def register_subscription(
    session: BullhornSession,
    subscription_id: str,
    entities: list[str],
) -> dict:
    """PUT /event/subscription/{id} — register or refresh the subscription."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            f"{session.rest_url}/event/subscription/{subscription_id}",
            params={
                "BhRestToken": session.rest_token,
                "type": "entity",
                "names": ",".join(entities),
                "eventTypes": "INSERTED,UPDATED,DELETED",
            },
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Subscription register failed {resp.status_code}: {resp.text[:500]}"
            )
        data = resp.json()
        log.info("[poller] Subscription registered: %s entities=%s", subscription_id, entities)
        return data


async def get_or_register_subscription(
    conn: asyncpg.Connection,
    session: BullhornSession,
    tenant_id: str,
    tenant_slug: str,
) -> tuple[str, int]:
    """
    Check subscription_state for an existing cursor; register with Bullhorn
    if not present. Returns (subscription_id, last_request_id).
    """
    sub_id = _subscription_id(tenant_slug)

    row = await conn.fetchrow(
        "SELECT last_request_id FROM subscription_state WHERE tenant_id=$1::uuid AND subscription_id=$2",
        tenant_id, sub_id,
    )

    last_request_id = row["last_request_id"] if row else 0
    now = datetime.datetime.now(datetime.timezone.utc)

    if not row:
        # First run — subscription was created manually via Postman, just record it.
        await conn.execute(
            """
            INSERT INTO subscription_state
                (tenant_id, subscription_id, last_request_id, entity_types, registered_at, updated_at)
            VALUES ($1::uuid, $2, $3, $4::text[], $5, $5)
            """,
            tenant_id, sub_id, last_request_id, SUBSCRIBED_ENTITIES, now,
        )
        log.info("[poller] Subscription state initialised. id=%s cursor=%d", sub_id, last_request_id)
    else:
        log.info("[poller] Resuming existing subscription. id=%s cursor=%d", sub_id, last_request_id)

    return sub_id, last_request_id


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

class SubscriptionExpiredError(RuntimeError):
    """Raised when Bullhorn returns 404 on poll — subscription has expired (>24h without polling)."""


async def poll_once(
    session: BullhornSession,
    subscription_id: str,
) -> tuple[int, list[dict]]:
    """
    GET /event/subscription/{id} — returns (requestId, events).
    Empty events list is normal (no changes since last poll).
    Raises SubscriptionExpiredError on 404 so the caller can re-register.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{session.rest_url}/event/subscription/{subscription_id}",
            params={
                "BhRestToken": session.rest_token,
                "maxEvents": MAX_EVENTS_PER_POLL,
            },
        )
        if resp.status_code == 404:
            raise SubscriptionExpiredError(
                f"Subscription {subscription_id!r} not found on Bullhorn (expired after >24h without polling)"
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Subscription poll failed {resp.status_code}: {resp.text[:500]}"
            )
        data = resp.json() if resp.content else {}

    request_id: int = data.get("requestId", 0)
    events: list[dict] = data.get("events", [])
    return request_id, events


async def update_cursor(
    conn: asyncpg.Connection,
    tenant_id: str,
    subscription_id: str,
    request_id: int,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    await conn.execute(
        """
        UPDATE subscription_state
        SET last_request_id = $3,
            last_polled_at  = $4,
            updated_at      = $4
        WHERE tenant_id = $1::uuid AND subscription_id = $2
        """,
        tenant_id, subscription_id, request_id, now,
    )


# ---------------------------------------------------------------------------
# Tenant resolution
# ---------------------------------------------------------------------------

async def resolve_tenant(conn: asyncpg.Connection, tenant_slug: str) -> str:
    """Return tenant UUID string for the given slug."""
    row = await conn.fetchrow(
        "SELECT id FROM tenants WHERE slug=$1 OR name=$1",
        tenant_slug,
    )
    if not row:
        raise RuntimeError(f"Tenant not found: {tenant_slug!r}")
    return str(row["id"])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_poller(tenant_slug: str) -> None:
    database_url = os.environ.get("DATABASE_ADMIN_URL") or os.environ["DATABASE_URL"]
    parsed = parse_db_url(database_url)
    sqs = _sqs_client()

    log.info("[poller] Starting — tenant=%s poll_interval=%ds", tenant_slug, POLL_INTERVAL_SECONDS)

    conn = await asyncpg.connect(**parsed)
    try:
        tenant_id = await resolve_tenant(conn, tenant_slug)
        session = await get_session()
        log.info("[poller] Authenticated with Bullhorn")

        subscription_id, _cursor = await get_or_register_subscription(
            conn, session, tenant_id, tenant_slug
        )

        consecutive_errors = 0
        while True:
            try:
                # Proactively refresh token if expiring within 2 minutes
                if session.expiring_soon():
                    log.info("[poller] Token expiring soon — refreshing proactively")
                    session = await refresh_session(session)
                    log.info("[poller] Token refreshed. expires_at=%s", session.expires_at.isoformat())

                request_id, events = await poll_once(session, subscription_id)

                if events:
                    log.info("[poller] %d event(s) received", len(events))
                    publish_events(sqs, tenant_id, events)
                else:
                    log.debug("[poller] No events")

                await update_cursor(conn, tenant_id, subscription_id, request_id)
                consecutive_errors = 0

            except SubscriptionExpiredError as e:
                # Subscription expired because poller was down >24h. Re-register
                # with Bullhorn — cursor resets to 0 on their side. Update our DB
                # to match. The nightly batch sync covers any events missed in the gap.
                log.warning("[poller] %s", e)
                log.warning("[poller] Re-registering subscription — cursor will reset to 0. Nightly batch will cover the gap.")
                try:
                    reg = await register_subscription(session, subscription_id, SUBSCRIBED_ENTITIES)
                    new_cursor = reg.get("requestId", 0)
                    await update_cursor(conn, tenant_id, subscription_id, new_cursor)
                    log.info("[poller] Re-registered. New cursor=%d", new_cursor)
                    consecutive_errors = 0
                except Exception as reg_err:
                    log.error("[poller] Re-registration failed: %s", reg_err)
                    consecutive_errors += 1

            except RuntimeError as e:
                consecutive_errors += 1
                err_str = str(e)
                log.error("[poller] Error (%d consecutive): %s", consecutive_errors, err_str)

                # Re-authenticate on unexpected session expiry (safety net)
                if any(x in err_str for x in ("401", "expired", "BhRestToken", "Invalid token")):
                    log.info("[poller] Unexpected 401 — re-authenticating...")
                    try:
                        session = await get_session()
                        log.info("[poller] Re-authenticated successfully. expires_at=%s", session.expires_at.isoformat())
                        consecutive_errors = 0
                    except Exception as auth_err:
                        log.error("[poller] Re-auth failed: %s", auth_err)

                # Back off after repeated errors (max 5 min)
                if consecutive_errors >= 3:
                    backoff = min(consecutive_errors * 60, 300)
                    log.warning("[poller] Backing off %ds after %d errors", backoff, consecutive_errors)
                    await asyncio.sleep(backoff)
                    continue

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bullhorn Event Subscription poller")
    parser.add_argument(
        "--tenant",
        default=os.getenv("STAFFINGAGENT_TENANT", "default"),
        help="Tenant slug or name (default: STAFFINGAGENT_TENANT env var)",
    )
    args = parser.parse_args()
    asyncio.run(run_poller(args.tenant))


if __name__ == "__main__":
    main()
