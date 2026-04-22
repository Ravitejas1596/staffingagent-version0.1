"""Seed 5 demo Time Anomaly alerts covering A1/A2/B/C for the demo tenant.

Purpose
-------
Lets Chris open a freshly-deployed Command Center, click into the Alert
Queue, and have realistic examples across all detector groups already in
place for pilot walkthroughs.

What gets seeded
----------------
- 1 × ``group_a1_first_miss``       (state: outreach_sent — reminder just went)
- 1 × ``group_a2_consecutive_miss`` (state: escalated_hitl — human needed)
- 1 × ``group_b_ot_over_limit``     (state: escalated_hitl — OT above cap)
- 1 × ``group_b_total_over_limit``  (state: resolved + employee_corrected —
                                     shows what "auto-resolved" looks like)
- 1 × ``group_c_variance``          (state: outreach_sent — variance alert)

Each alert gets one matching ``agent_alert_events`` row so the timeline
view in the drawer isn't empty.

Safety
------
- Targets ``TENANT_ID`` explicitly. Rows created here are idempotent by
  ``id`` (UUID5 from a namespace) — rerunning the script won't duplicate.
- Uses ``SET LOCAL app.bypass_rls = 'on'`` so the raw SQL inserts aren't
  blocked by RLS (Postgres role still needs ``BYPASSRLS`` or the
  ``app.bypass_rls`` toggle registered in migration 045).
- Skips insert entirely if the target tenant does not exist — avoids
  FK errors on a fresh DB without the pilot bootstrap run yet.

Usage
-----
::

    DATABASE_URL="postgresql://postgres:localpass@localhost:5434/staffingagent" \\
        python3 deploy/db/seeds/time_anomaly_demo_seed.py
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import uuid
from typing import Any

import asyncpg

# Demo tenant — same ID used by ``vms_seed.py``. If Chris ever changes
# the pilot tenant, update both in one commit.
TENANT_ID = "4b38b488-bdd4-4973-b2b5-6994852ee4bd"

# Stable namespace so rerunning the script reuses the same alert IDs.
# Pick any UUID5 namespace — this one is fine because we never expose
# the IDs outside seed data.
_NS = uuid.UUID("00000000-0000-0000-0000-deadbeefcafe")


def _deterministic_alert_id(alert_type: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"time-anomaly-demo::{alert_type}")


def _current_cycle() -> tuple[datetime.date, datetime.date]:
    """Most recent Mon → Sun timesheet cycle."""
    today = datetime.date.today()
    # Back up to last Monday
    days_since_monday = today.weekday()
    cycle_start = today - datetime.timedelta(days=days_since_monday + 7)
    cycle_end = cycle_start + datetime.timedelta(days=6)
    return cycle_start, cycle_end


def _prior_cycle(
    start: datetime.date, n: int
) -> tuple[datetime.date, datetime.date]:
    s = start - datetime.timedelta(days=7 * n)
    return s, s + datetime.timedelta(days=6)


DEMO_ALERTS: list[dict[str, Any]] = [
    {
        "alert_type": "group_a1_first_miss",
        "severity": "medium",
        "state": "outreach_sent",
        "resolution": None,
        "trigger_context": {
            "reason": "no_timesheet_past_due",
            "placement_bullhorn_id": "P-10021",
            "hours_past_cycle_end": 18.0,
            "candidate_name_redacted": "J. Doe",
        },
        "event": {
            "event_type": "outreach_sent",
            "actor_type": "agent",
            "metadata": {
                "channel": "sms",
                "template_key": "time_anomaly.group_a1.sms",
                "sms_sid": "SMdemo0001",
            },
        },
        "periods_back": 0,
    },
    {
        "alert_type": "group_a2_consecutive_miss",
        "severity": "high",
        "state": "escalated_hitl",
        "resolution": None,
        "trigger_context": {
            "reason": "consecutive_miss_no_timesheet",
            "placement_bullhorn_id": "P-10044",
            "consecutive_cycles_missed": 3,
        },
        "event": {
            "event_type": "escalated_to_hitl",
            "actor_type": "agent",
            "metadata": {"escalation_reason": "no_response_after_reminder"},
        },
        "periods_back": 0,
    },
    {
        "alert_type": "group_b_ot_over_limit",
        "severity": "high",
        "state": "escalated_hitl",
        "resolution": None,
        "trigger_context": {
            "reason": "ot_over_limit",
            "placement_bullhorn_id": "P-10067",
            "timesheet_id": "TS-88231",
            "reported_ot_hours": 28.5,
            "configured_limit": 20.0,
        },
        "event": {
            "event_type": "escalated_to_hitl",
            "actor_type": "agent",
            "metadata": {"escalation_reason": "ot_above_hard_cap"},
        },
        "periods_back": 0,
    },
    {
        "alert_type": "group_b_total_over_limit",
        "severity": "medium",
        "state": "resolved",
        "resolution": "employee_corrected",
        "trigger_context": {
            "reason": "total_over_limit",
            "placement_bullhorn_id": "P-10078",
            "timesheet_id": "TS-88412",
            "reported_total_hours": 68.0,
            "configured_limit": 60.0,
        },
        "event": {
            "event_type": "resolved",
            "actor_type": "agent",
            "metadata": {
                "resolution_source": "auto_recheck",
                "note": "employee resubmitted with corrected total 58.0",
            },
        },
        "periods_back": 1,
    },
    {
        "alert_type": "group_c_variance",
        "severity": "medium",
        "state": "outreach_sent",
        "resolution": None,
        "trigger_context": {
            "reason": "variance_from_typical",
            "placement_bullhorn_id": "P-10091",
            "timesheet_id": "TS-88590",
            "reported_total_hours": 12.0,
            "typical_total_hours": 40.0,
            "magnitude_multiplier": 3.33,
        },
        "event": {
            "event_type": "outreach_sent",
            "actor_type": "agent",
            "metadata": {
                "channel": "sms",
                "template_key": "time_anomaly.group_c.sms",
                "sms_sid": "SMdemo0005",
            },
        },
        "periods_back": 0,
    },
]


async def _tenant_exists(conn: asyncpg.Connection, tenant_id: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM tenants WHERE id = $1::uuid", tenant_id
    )
    return row is not None


async def seed(conn: asyncpg.Connection) -> None:
    if not await _tenant_exists(conn, TENANT_ID):
        print(
            f"Tenant {TENANT_ID} does not exist yet — skipping demo alert "
            "seed. Run the pilot bootstrap first."
        )
        return

    await conn.execute("SET LOCAL app.bypass_rls = 'on'")

    cycle_start, cycle_end = _current_cycle()
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    inserted = 0

    for alert in DEMO_ALERTS:
        alert_id = _deterministic_alert_id(alert["alert_type"])
        period_start, period_end = _prior_cycle(
            cycle_start, alert["periods_back"]
        )

        detected_at = now - datetime.timedelta(hours=6)
        outreach_sent_at = (
            now - datetime.timedelta(hours=5)
            if alert["state"]
            in ("outreach_sent", "escalated_hitl", "resolved")
            else None
        )
        escalated_at = (
            now - datetime.timedelta(hours=2)
            if alert["state"] == "escalated_hitl"
            else None
        )
        resolved_at = now if alert["state"] == "resolved" else None

        # Upsert the alert row.
        await conn.execute(
            """
            INSERT INTO agent_alerts (
                id, tenant_id, agent_type, alert_type, severity, state,
                resolution, pay_period_start, pay_period_end,
                trigger_context, detected_at, outreach_sent_at,
                escalated_at, resolved_at
            )
            VALUES (
                $1::uuid, $2::uuid, 'time_anomaly', $3, $4, $5,
                $6, $7, $8, $9::jsonb, $10, $11, $12, $13
            )
            ON CONFLICT (id) DO UPDATE SET
                state = EXCLUDED.state,
                resolution = EXCLUDED.resolution,
                trigger_context = EXCLUDED.trigger_context,
                outreach_sent_at = EXCLUDED.outreach_sent_at,
                escalated_at = EXCLUDED.escalated_at,
                resolved_at = EXCLUDED.resolved_at
            """,
            str(alert_id),
            TENANT_ID,
            alert["alert_type"],
            alert["severity"],
            alert["state"],
            alert["resolution"],
            period_start,
            period_end,
            json.dumps(alert["trigger_context"]),
            detected_at,
            outreach_sent_at,
            escalated_at,
            resolved_at,
        )

        # One supporting event — keep it idempotent by deleting
        # prior demo events for this alert before inserting.
        await conn.execute(
            "DELETE FROM agent_alert_events WHERE alert_id = $1::uuid AND actor_id = 'demo_seed'",
            str(alert_id),
        )
        await conn.execute(
            """
            INSERT INTO agent_alert_events (
                id, alert_id, tenant_id, event_type, actor_type,
                actor_id, metadata
            ) VALUES (
                gen_random_uuid(), $1::uuid, $2::uuid, $3, $4,
                'demo_seed', $5::jsonb
            )
            """,
            str(alert_id),
            TENANT_ID,
            alert["event"]["event_type"],
            alert["event"]["actor_type"],
            json.dumps(alert["event"]["metadata"]),
        )
        inserted += 1
        print(f"seeded {alert['alert_type']:32s} -> state={alert['state']}")

    print(f"\nInserted/refreshed {inserted} demo Time Anomaly alerts for tenant {TENANT_ID}")


async def main() -> None:
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:localpass@localhost:5434/staffingagent",
    )
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(db_url)
    try:
        async with conn.transaction():
            await seed(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
