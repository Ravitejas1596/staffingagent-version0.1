"""
Run a SQL migration file against the database.

Usage:
    python -m src.sync.migrate deploy/db/migrations/014_combined_field_expansion.sql
"""
import asyncio
import os
import sys

import asyncpg

from src.sync._db import parse_db_url


async def main(sql_file: str) -> None:
    db_url = os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if not db_url:
        raise ValueError("MIGRATION_DATABASE_URL or DATABASE_URL is not set")

    sql = open(sql_file).read()
    print(f"Running migration: {sql_file}")

    kwargs = parse_db_url(db_url)
    conn = await asyncpg.connect(**kwargs)
    try:
        await conn.execute(sql)
        print("Migration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.sync.migrate <sql_file>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
