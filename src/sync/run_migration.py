"""
Run a SQL migration file against the StaffingAgent database.

Usage (as one-off ECS task command override):
    python -m src.sync.run_migration deploy/db/migrations/001_pay_bill_tables.sql
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

from src.sync._db import parse_db_url


async def main(sql_file: str) -> None:
    # Migrations require the admin (postgres) user, not app_user
    admin_url = os.environ.get("DATABASE_ADMIN_URL") or os.environ["DATABASE_URL"]
    db_params = parse_db_url(admin_url)
    with open(sql_file) as f:
        sql = f.read()
    conn = await asyncpg.connect(**db_params)
    try:
        await conn.execute(sql)
        print(f"Migration complete: {sql_file}")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.sync.run_migration <path/to/migration.sql>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
