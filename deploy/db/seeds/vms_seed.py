"""
Seed fake VMS records for testing the VMS Reconciliation matching agent.

Candidates are drawn from real placements in the DB. VMS names are deliberately
fuzzy — truncated, misspelled, hyphenated differently, first/last swapped, etc. —
to exercise the matching agent.

Usage:
    DATABASE_URL="postgresql://postgres:localpass@localhost:5434/staffingagent" \
        python3 deploy/db/seeds/vms_seed.py
"""
import asyncio
import datetime
import os
import random
import uuid

import asyncpg

TENANT_ID = "4b38b488-bdd4-4973-b2b5-6994852ee4bd"

# Real candidate names from placements + their canonical bill rates
# (first, last, bill_rate, client, placement_ref)
REAL_CANDIDATES = [
    ("Yuri",        "Zabara",       1430.00, "Government of Nunavut",             "P-245"),
    ("Rahman",      "Labibi",       1427.50, "Government of Nunavut",             "P-071"),
    ("Farrukh",     "Siddique",     1315.00, "Government of Nunavut",             "P-230"),
    ("Justin",      "van Niekerk",  1290.00, "Government of Nunavut",             "P-148"),
    ("Jonathan",    "Moraal",       1282.50, "Government of Nunavut",             "P-289"),
    ("Jibril",      "Esak",         1240.00, "Government of Nunavut",             "P-444"),
    ("JOY",         "GROVES",       1190.00, "Government of Nunavut",             "P-092"),
    ("Mladen",      "Jaksic",       1150.00, "OPS Ministry of Government Services","P-207"),
    ("Steve",       "Labrecque",    1150.00, "OPS Ministry of Health",            "P-439"),
    ("Aleksandar",  "Nojkov",       1100.00, "Roy Industries",                    "P-458"),
    ("Abdulqadir",  "Galan",        1090.00, "Government of Nunavut",             "P-033"),
    ("Akhtar",      "Ali",          1090.00, "Government of Nunavut",             "P-139"),
    ("James",       "Finnie",       1050.00, "National Research Council",         "P-160"),
    ("Aiyesvarie",  "Vairavanathan", 34.48, "Roy Industries",                    "P-377"),
    ("Kenia",       "Veloz",         70.00, "Procom Consultants Group",           "P-405"),
    ("Umar",        "Muhammad",      89.65, "Roy Industries",                    "P-269"),
    ("Mohamed",     "Osman",         89.66, "Roy Industries",                    "P-470"),
    ("Yana",        "Almeida",       72.41, "Roy Industries",                    "P-417"),
    ("Saeid",       "Ageorlo",      131.03, "OPS eHealth Ontario",               "P-306"),
    ("Anisa",       "Shire",        525.00, "Roy Industries",                    "P-110"),
    ("Shawn",       "Suman",        166.67, "Government of Nunavut",             "P-400"),
    ("Shaira",      "Addetia",      370.00, "Orion Health",                      "P-041"),
    ("Ryan",        "McCormack",     85.00, "Interac Association",               "P-046"),
    ("Charmaine",   "Flowers",       15.00, "NBA All-Star Program",              "P-116"),
    ("Christine",   "Yeh",           15.00, "NBA All-Star Program",              "P-276"),
]

VMS_PLATFORMS = ["Fieldglass", "Beeline", "IQNavigator", "Coupa", "Workday VMS"]


def _fuzzy_name(first: str, last: str) -> str:
    """Return a slightly wrong version of the name for VMS fuzzy matching tests."""
    strategies = [
        # Perfect match (30% of the time — these should be easy matches)
        lambda f, l: f"{f} {l}",
        lambda f, l: f"{f} {l}",
        lambda f, l: f"{f} {l}",
        # Last, First format
        lambda f, l: f"{l}, {f}",
        # First initial only
        lambda f, l: f"{f[0]}. {l}",
        # Truncated first name
        lambda f, l: f"{f[:max(2,len(f)-2)]} {l}",
        # Typo: drop a letter from last name
        lambda f, l: f"{f} {l[:-1]}" if len(l) > 3 else f"{f} {l}",
        # Double letter in last name
        lambda f, l: f"{f} {l[0]}{l}",
        # Lowercase everything
        lambda f, l: f"{f.lower()} {l.lower()}",
        # ALL CAPS
        lambda f, l: f"{f.upper()} {l.upper()}",
        # Middle initial inserted
        lambda f, l: f"{f} J. {l}",
        # Hyphenated last name variation
        lambda f, l: f"{f} {l}-Smith" if len(l) > 4 else f"{f} {l}",
        # Nickname (shorten first)
        lambda f, l: f"{f[:3]} {l}",
        # Swapped first/last
        lambda f, l: f"{l} {f}",
        # Extra space
        lambda f, l: f"{f}  {l}",
    ]
    fn = random.choice(strategies)
    return fn(first, last)


def _week_endings(num_weeks: int = 12) -> list[datetime.date]:
    """Return the last N Friday week-ending dates."""
    today = datetime.date.today()
    # Find the most recent Friday
    days_since_friday = (today.weekday() - 4) % 7
    last_friday = today - datetime.timedelta(days=days_since_friday)
    return [last_friday - datetime.timedelta(weeks=i) for i in range(num_weeks)]


async def seed(conn: asyncpg.Connection) -> None:
    week_endings = _week_endings(12)
    upload_id = str(uuid.uuid4())
    platform = random.choice(VMS_PLATFORMS)

    # Create a fake upload record
    await conn.execute(
        """
        INSERT INTO vms_uploads (id, tenant_id, filename, s3_key, vms_platform, record_count, status, completed_at)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, 'completed', now())
        """,
        upload_id,
        TENANT_ID,
        f"vms_export_{datetime.date.today()}.csv",
        f"{TENANT_ID}/{upload_id}/vms_export.csv",
        platform,
        len(REAL_CANDIDATES) * len(week_endings),
    )
    print(f"Created vms_upload: {upload_id} ({platform})")

    rows_inserted = 0
    for candidate in REAL_CANDIDATES:
        first, last, bill_rate, client, placement_ref = candidate

        for week_ending in week_endings:
            # Decide hours — mostly normal, occasional anomalies
            roll = random.random()
            if roll < 0.05:
                regular_hours = 40.0
                ot_hours = round(random.uniform(8, 20), 2)   # overtime spike
            elif roll < 0.10:
                regular_hours = 0.0
                ot_hours = 0.0                                # missing / no-show
            else:
                regular_hours = round(random.choice([37.5, 40.0, 35.0, 40.0, 37.5]), 2)
                ot_hours = round(random.choice([0, 0, 0, 0, 2.5, 5.0]), 2)

            # Rate variance: 70% exact, 20% slightly off, 10% wrong rate
            rate_roll = random.random()
            if rate_roll < 0.70:
                vms_rate = bill_rate
            elif rate_roll < 0.90:
                vms_rate = round(bill_rate * random.uniform(0.97, 1.03), 2)
            else:
                vms_rate = round(bill_rate * random.uniform(0.85, 1.15), 2)

            total = round((regular_hours * vms_rate) + (ot_hours * vms_rate * 1.5), 2)

            vms_name = _fuzzy_name(first, last)

            await conn.execute(
                """
                INSERT INTO vms_records (
                    id, tenant_id, upload_id, vms_platform, placement_ref,
                    candidate_name, week_ending,
                    regular_hours, ot_hours, bill_rate, ot_rate,
                    per_diem, total_amount, status, source_type, raw_data
                ) VALUES (
                    gen_random_uuid(), $1::uuid, $2::uuid, $3, $4,
                    $5, $6,
                    $7, $8, $9, $10,
                    0, $11, 'pending', 'file', $12
                )
                """,
                TENANT_ID,
                upload_id,
                platform,
                placement_ref,
                vms_name,
                week_ending,
                regular_hours,
                ot_hours,
                vms_rate,
                round(vms_rate * 1.5, 2),
                total,
                f'{{"raw_first": "{first}", "raw_last": "{last}", "source": "seed"}}',
            )
            rows_inserted += 1

    print(f"Inserted {rows_inserted} VMS records across {len(week_endings)} weeks for {len(REAL_CANDIDATES)} candidates.")
    print("Name fuzzing applied — expect ~70% exact, ~30% fuzzy matches.")


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:localpass@localhost:5434/staffingagent")
    # asyncpg needs plain postgresql:// not postgresql+asyncpg://
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(db_url)
    try:
        await seed(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
