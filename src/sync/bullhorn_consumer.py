"""
Bullhorn SQS event consumer — processes change events published by bullhorn_poller.py.

Reads batches from the bullhorn-events SQS queue, fetches full records from
Bullhorn for each changed entity ID, and upserts them to Aurora using the
existing sync functions.

BillMaster, BillMasterTransaction, PayMaster, PayMasterTransaction events are
received and logged but not upserted — we don't sync those entity tables yet.

Usage:
    python -m src.sync.bullhorn_consumer                    # uses STAFFINGAGENT_TENANT env
    python -m src.sync.bullhorn_consumer --tenant default

Required env vars: BULLHORN_* (see bullhorn_auth.py), DATABASE_URL,
                   BULLHORN_EVENTS_QUEUE_URL, AWS_DEFAULT_REGION
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any

import asyncpg
import boto3

from src.sync._db import parse_db_url
from src.sync.bullhorn_auth import BullhornSession, bullhorn_query, get_session, refresh_session
from src.sync.bullhorn_sync import (
    BILLABLE_CHARGE_FIELDS,
    CANDIDATE_FIELDS,
    CLIENT_CORPORATION_FIELDS,
    INVOICE_FIELDS,
    JOB_ORDER_FIELDS,
    PAYABLE_CHARGE_FIELDS,
    PLACEMENT_FIELDS,
    TIMESHEET_FIELDS,
    _record_sync,
    sync_billable_charges,
    sync_candidates,
    sync_client_corporations,
    sync_invoices,
    sync_job_orders,
    sync_payable_charges,
    sync_placements,
    sync_timesheets,
)

log = logging.getLogger("bullhorn_consumer")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

QUEUE_URL = os.environ.get("BULLHORN_EVENTS_QUEUE_URL", "")
POLL_WAIT_SECONDS = 20   # SQS long-poll
MAX_MESSAGES = 10        # SQS max per receive call

# Entities we have Aurora tables + upsert functions for
ENTITY_HANDLERS: dict[str, tuple[str, Any]] = {
    "Placement":         (PLACEMENT_FIELDS,          sync_placements),
    "Timesheet":         (TIMESHEET_FIELDS,           sync_timesheets),
    "BillableCharge":    (BILLABLE_CHARGE_FIELDS,     sync_billable_charges),
    "PayableCharge":     (PAYABLE_CHARGE_FIELDS,      sync_payable_charges),
    "Candidate":         (CANDIDATE_FIELDS,           sync_candidates),
    "ClientCorporation": (CLIENT_CORPORATION_FIELDS,  sync_client_corporations),
    "JobOrder":          (JOB_ORDER_FIELDS,           sync_job_orders),
    "InvoiceStatement":  (INVOICE_FIELDS,             sync_invoices),
}

ENTITY_SYNC_KEY: dict[str, str] = {
    "Placement":         "placements",
    "Timesheet":         "timesheets",
    "BillableCharge":    "billable_charges",
    "PayableCharge":     "payable_charges",
    "Candidate":         "candidates",
    "ClientCorporation": "client_corporations",
    "JobOrder":          "job_orders",
    "InvoiceStatement":  "invoices",
}

# Received in subscription but no Aurora table yet — log only
UNHANDLED_ENTITIES = {"BillMaster", "BillMasterTransaction", "PayMaster", "PayMasterTransaction"}


# ---------------------------------------------------------------------------
# Event processing
# ---------------------------------------------------------------------------

async def process_events(
    conn: asyncpg.Connection,
    session: BullhornSession,
    tenant_id: str,
    events: list[dict],
) -> None:
    """
    Group events by entityType, fetch full records for INSERTED/UPDATED IDs,
    upsert via existing sync functions. DELETED events are logged only.
    Unhandled entity types (BillMaster etc.) are logged only.
    """
    inserts_updates: dict[str, set[int]] = defaultdict(set)
    deletes: dict[str, set[int]] = defaultdict(set)

    for ev in events:
        entity_type = ev.get("entityType", "")
        entity_id = ev.get("entityId")
        event_type = ev.get("eventType", "")

        if entity_type in UNHANDLED_ENTITIES:
            log.debug("[consumer] %s %s id=%s — no handler yet, skipping",
                      event_type, entity_type, entity_id)
            continue

        if entity_type not in ENTITY_HANDLERS:
            log.debug("[consumer] Unknown entity type: %s", entity_type)
            continue

        if entity_id is None:
            continue

        if event_type == "DELETED":
            deletes[entity_type].add(int(entity_id))
        else:
            inserts_updates[entity_type].add(int(entity_id))

    # Process inserts/updates
    for entity_type, ids in inserts_updates.items():
        fields, sync_fn = ENTITY_HANDLERS[entity_type]
        sync_key = ENTITY_SYNC_KEY[entity_type]
        id_list = sorted(ids)

        log.info("[consumer] Fetching %d changed %s record(s): %s",
                 len(id_list), entity_type, id_list[:10])

        all_records: list[dict] = []
        batch_size = 50
        for i in range(0, len(id_list), batch_size):
            batch = id_list[i:i + batch_size]
            id_csv = ",".join(str(x) for x in batch)
            try:
                page = await bullhorn_query(
                    session,
                    entity_type,
                    fields,
                    where=f"id IN ({id_csv})",
                    count=batch_size,
                    start=0,
                )
                all_records.extend(page.get("data", []))
            except RuntimeError as e:
                log.error("[consumer] Failed to fetch %s ids=%s: %s", entity_type, batch, e)

        if all_records:
            count = await sync_fn(conn, tenant_id, all_records)
            await _record_sync(conn, tenant_id, sync_key, count)
            log.info("[consumer] Upserted %d %s record(s)", count, entity_type)

    # Log deletes
    for entity_type, ids in deletes.items():
        log.warning("[consumer] DELETED %s ids=%s — skipped (nightly sync reconciles)",
                    entity_type, sorted(ids))


# ---------------------------------------------------------------------------
# SQS receive loop
# ---------------------------------------------------------------------------

async def process_message(
    sqs: Any,
    conn: asyncpg.Connection,
    session: BullhornSession,
    msg: dict,
) -> None:
    """Parse one SQS message and process its events."""
    receipt = msg["ReceiptHandle"]
    try:
        payload = json.loads(msg["Body"])
        tenant_id: str = payload["tenant_id"]
        events: list[dict] = payload["events"]
        log.info("[consumer] Processing %d event(s) from SQS", len(events))
        await process_events(conn, session, tenant_id, events)
        sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)
    except Exception as e:
        log.error("[consumer] Failed to process message — leaving in queue for retry: %s", e)
        raise


async def run_consumer(tenant_slug: str) -> None:
    if not QUEUE_URL:
        raise RuntimeError("BULLHORN_EVENTS_QUEUE_URL is not set")

    database_url = os.environ["DATABASE_URL"]
    parsed = parse_db_url(database_url)
    sqs = boto3.client("sqs", region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

    log.info("[consumer] Starting — tenant=%s queue=%s", tenant_slug, QUEUE_URL)

    conn = await asyncpg.connect(**parsed)
    try:
        session = await get_session()
        log.info("[consumer] Authenticated with Bullhorn")

        consecutive_errors = 0
        while True:
            try:
                # Proactively refresh token if expiring within 2 minutes
                if session.expiring_soon():
                    log.info("[consumer] Token expiring soon — refreshing proactively")
                    session = await refresh_session(session)
                    log.info("[consumer] Token refreshed. expires_at=%s", session.expires_at.isoformat())

                resp = sqs.receive_message(
                    QueueUrl=QUEUE_URL,
                    MaxNumberOfMessages=MAX_MESSAGES,
                    WaitTimeSeconds=POLL_WAIT_SECONDS,
                    MessageAttributeNames=["All"],
                )
                messages = resp.get("Messages", [])

                if not messages:
                    log.debug("[consumer] No messages")
                    continue

                for msg in messages:
                    await process_message(sqs, conn, session, msg)

                consecutive_errors = 0

            except RuntimeError as e:
                consecutive_errors += 1
                err_str = str(e)
                log.error("[consumer] Error (%d consecutive): %s", consecutive_errors, err_str)

                if any(x in err_str for x in ("401", "expired", "BhRestToken", "Invalid token")):
                    log.info("[consumer] Re-authenticating with Bullhorn...")
                    try:
                        session = await get_session()
                        log.info("[consumer] Re-authenticated successfully")
                        consecutive_errors = 0
                    except Exception as auth_err:
                        log.error("[consumer] Re-auth failed: %s", auth_err)

                if consecutive_errors >= 3:
                    backoff = min(consecutive_errors * 60, 300)
                    log.warning("[consumer] Backing off %ds", backoff)
                    await asyncio.sleep(backoff)

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bullhorn SQS event consumer")
    parser.add_argument(
        "--tenant",
        default=os.getenv("STAFFINGAGENT_TENANT", "default"),
        help="Tenant slug or name (default: STAFFINGAGENT_TENANT env var)",
    )
    args = parser.parse_args()
    asyncio.run(run_consumer(args.tenant))


if __name__ == "__main__":
    main()
