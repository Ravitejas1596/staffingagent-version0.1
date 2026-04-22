"""Automated database migration runner for StaffingAgent.

Scans deploy/db/migrations/ for numbered SQL files (NNN_name.sql),
tracks applied migrations in a schema_migrations table, and applies
pending ones in order. Uses a PostgreSQL advisory lock to prevent
concurrent runs (e.g. multiple ECS tasks starting simultaneously).

Auto-baseline: when the tracking table has no entries but application
tables already exist, the runner attempts each migration and treats
failures as "already applied" so they won't be retried. Only genuinely
new migrations must succeed.

Usage:
    python -m deploy.db.migrate          # apply pending migrations
    python -m deploy.db.migrate --status # show applied vs pending

Requires DATABASE_ADMIN_URL or DATABASE_URL environment variable.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import traceback
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
ADVISORY_LOCK_ID = 7_483_647_001  # arbitrary unique int64 for pg_advisory_lock

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def log(msg: str) -> None:
    """Print to stdout with flush so CloudWatch captures it immediately."""
    print(msg, flush=True)


def _parse_dsn(url: str) -> str:
    """Convert SQLAlchemy-style URLs to plain asyncpg DSN."""
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _redact_dsn(url: str) -> str:
    """Hide password in DSN for safe logging."""
    return re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", url)


def _strip_transaction_wrappers(sql: str) -> str:
    """Remove explicit BEGIN/COMMIT so the runner can manage transactions."""
    sql = re.sub(r"(?i)^\s*BEGIN\s*;\s*$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"(?i)^\s*COMMIT\s*;\s*$", "", sql, flags=re.MULTILINE)
    return sql.strip()


def _discover_migrations() -> list[tuple[str, str, Path]]:
    """Return sorted list of (version, filename, path) for all numbered SQL files."""
    pattern = re.compile(r"^(\d{3})_.+\.sql$")
    migrations = []
    if not MIGRATIONS_DIR.exists():
        log(f"WARNING: migrations directory does not exist: {MIGRATIONS_DIR}")
        return migrations
    for f in sorted(MIGRATIONS_DIR.iterdir()):
        m = pattern.match(f.name)
        if m:
            migrations.append((m.group(1), f.name, f))
    return migrations


async def _ensure_tracking_table(conn: asyncpg.Connection) -> None:
    await conn.execute(SCHEMA_MIGRATIONS_DDL)


async def _needs_baseline(conn: asyncpg.Connection, applied: set[str]) -> bool:
    """Detect an existing database with no migration history.

    True when app tables exist (e.g. tenants) but the tracking table has
    no recorded migrations — meaning the DB predates the migration runner.
    """
    if applied:
        return False
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'tenants')"
    )


async def _applied_versions(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
    return {r["version"] for r in rows}


async def _apply_migration(
    conn: asyncpg.Connection,
    version: str,
    filename: str,
    path: Path,
    *,
    allow_baseline: bool = False,
) -> bool:
    """Apply a single migration. Returns True if applied, False if baselined."""
    raw_sql = path.read_text(encoding="utf-8")
    sql = _strip_transaction_wrappers(raw_sql)

    log(f"  [{version}] {filename} ...")
    try:
        async with conn.transaction():
            await conn.execute(sql)
        await conn.execute(
            "INSERT INTO schema_migrations (version, filename) VALUES ($1, $2)",
            version,
            filename,
        )
        log(f"  [{version}] applied")
        return True
    except Exception as e:
        if allow_baseline:
            await conn.execute(
                "INSERT INTO schema_migrations (version, filename) VALUES ($1, $2)",
                version,
                filename,
            )
            log(f"  [{version}] baselined ({type(e).__name__}: {e})")
            return False
        else:
            log(f"  [{version}] FAILED: {e}")
            raise


async def run(*, status_only: bool = False) -> int:
    log("=== StaffingAgent Migration Runner ===")

    dsn = os.environ.get("DATABASE_ADMIN_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        log("ERROR: Neither DATABASE_ADMIN_URL nor DATABASE_URL is set")
        log(f"  Available env vars: {sorted(k for k in os.environ if 'DATABASE' in k.upper())}")
        return 1

    dsn = _parse_dsn(dsn)
    log(f"DSN: {_redact_dsn(dsn)}")

    all_migrations = _discover_migrations()
    log(f"Found {len(all_migrations)} migration file(s) in {MIGRATIONS_DIR}")

    if not all_migrations:
        log("Nothing to do")
        return 0

    log("Connecting to database...")
    try:
        conn = await asyncpg.connect(dsn, timeout=30)
    except Exception as e:
        log(f"ERROR: Failed to connect to database: {type(e).__name__}: {e}")
        return 1

    try:
        server_version = conn.get_server_version()
        log(f"Connected (PostgreSQL {server_version[0]}.{server_version[1]})")

        await _ensure_tracking_table(conn)
        applied = await _applied_versions(conn)
        log(f"Already applied: {len(applied)} migration(s)")

        needs_baseline = await _needs_baseline(conn, applied)
        if needs_baseline:
            log("Auto-baseline mode: existing database detected without migration history")

        pending = [(v, fn, p) for v, fn, p in all_migrations if v not in applied]

        if status_only:
            log(f"Total: {len(all_migrations)} | Applied: {len(applied)} | Pending: {len(pending)}")
            if needs_baseline:
                log("  (auto-baseline mode active)")
            for v, fn, _ in pending:
                log(f"  {fn}")
            return 0

        if not pending:
            log("Database is up to date")
            return 0

        log(f"Acquiring advisory lock (id={ADVISORY_LOCK_ID})...")
        acquired = await conn.fetchval("SELECT pg_try_advisory_lock($1)", ADVISORY_LOCK_ID)
        if not acquired:
            log("Another migration process holds the lock — skipping")
            return 0
        log("Lock acquired")

        try:
            applied_count = 0
            baselined_count = 0
            log(f"Processing {len(pending)} pending migration(s):")

            for version, filename, path in pending:
                was_applied = await _apply_migration(
                    conn, version, filename, path,
                    allow_baseline=needs_baseline,
                )
                if was_applied:
                    applied_count += 1
                else:
                    baselined_count += 1

            total = len(applied) + applied_count + baselined_count
            parts = []
            if applied_count:
                parts.append(f"{applied_count} applied")
            if baselined_count:
                parts.append(f"{baselined_count} baselined")
            log(f"Done — {total} total migrations tracked ({', '.join(parts)})")
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)
            log("Lock released")
    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        await conn.close()
        log("Connection closed")

    return 0


def main() -> None:
    status_only = "--status" in sys.argv
    try:
        exit_code = asyncio.run(run(status_only=status_only))
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        traceback.print_exc()
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
