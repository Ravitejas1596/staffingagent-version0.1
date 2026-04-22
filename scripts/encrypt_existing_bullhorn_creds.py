"""One-shot + rotation script for Bullhorn credential encryption.

Two modes:
    Default:    re-encrypt every tenant whose bullhorn_credentials_ciphertext is
                NULL but whose bullhorn_config still has plaintext secrets.
                Safe to re-run — it is a no-op for already-encrypted rows.

    --rotate:   re-encrypt every tenant whose bullhorn_credentials_version is
                lower than the current key version. Use this after swapping
                BULLHORN_CREDS_KEK to pick up the new primary key.

Requires:
    DATABASE_ADMIN_URL   — Postgres connection string (superuser, to bypass RLS)
    BULLHORN_CREDS_KEK   — url-safe base64 32-byte Fernet key

Usage:
    python scripts/encrypt_existing_bullhorn_creds.py
    python scripts/encrypt_existing_bullhorn_creds.py --rotate
    python scripts/encrypt_existing_bullhorn_creds.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

import asyncpg

from app_platform.api.crypto import (
    current_key_version,
    decrypt_credentials,
    encrypt_credentials,
)


SECRET_FIELDS = ("client_id", "client_secret", "api_user", "api_password")


def _parse_dsn(url: str) -> str:
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


async def _fetch_candidates(conn: asyncpg.Connection, rotate: bool) -> list[dict]:
    if rotate:
        rows = await conn.fetch(
            """
            SELECT id, name, bullhorn_config, bullhorn_credentials_ciphertext,
                   bullhorn_credentials_version
            FROM tenants
            WHERE bullhorn_credentials_ciphertext IS NOT NULL
              AND bullhorn_credentials_version < $1
            """,
            current_key_version(),
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, name, bullhorn_config, bullhorn_credentials_ciphertext,
                   bullhorn_credentials_version
            FROM tenants
            WHERE bullhorn_credentials_ciphertext IS NULL
              AND bullhorn_config IS NOT NULL
              AND bullhorn_config ? 'client_id'
            """,
        )
    return [dict(r) for r in rows]


def _plaintext_from_row(row: dict) -> dict[str, str] | None:
    """Extract credential dict from either the legacy JSONB or the existing ciphertext."""
    if row.get("bullhorn_credentials_ciphertext"):
        try:
            return decrypt_credentials(bytes(row["bullhorn_credentials_ciphertext"]))
        except Exception as exc:
            print(f"  WARN: decrypt failed for tenant {row['id']}: {exc}", file=sys.stderr)
            return None
    cfg = row.get("bullhorn_config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    missing = [f for f in SECRET_FIELDS if not cfg.get(f)]
    if missing:
        print(f"  SKIP tenant {row['id']}: missing {missing}", file=sys.stderr)
        return None
    return {f: cfg[f] for f in SECRET_FIELDS}


def _stripped_config(row: dict) -> dict:
    cfg = row.get("bullhorn_config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    return {k: v for k, v in cfg.items() if k not in SECRET_FIELDS}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rotate", action="store_true",
                        help="Re-encrypt rows under the new primary key.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without writing.")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_ADMIN_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_ADMIN_URL or DATABASE_URL must be set", file=sys.stderr)
        return 1

    if not os.environ.get("BULLHORN_CREDS_KEK"):
        print("ERROR: BULLHORN_CREDS_KEK must be set", file=sys.stderr)
        return 1

    mode = "rotate" if args.rotate else "initial encryption"
    print(f"=== Bullhorn credential {mode} ===")
    if args.dry_run:
        print("DRY-RUN: no writes will be made")

    conn = await asyncpg.connect(_parse_dsn(dsn))
    try:
        rows = await _fetch_candidates(conn, args.rotate)
        print(f"Found {len(rows)} tenant(s) to process")

        updated = 0
        for row in rows:
            plaintext = _plaintext_from_row(row)
            if not plaintext:
                continue

            ciphertext = encrypt_credentials(plaintext)
            cleaned_cfg = _stripped_config(row)
            cleaned_cfg["configured_at"] = datetime.now(timezone.utc).isoformat()

            print(f"  tenant {row['id']} ({row.get('name')}): "
                  f"{len(ciphertext)} bytes ciphertext")

            if not args.dry_run:
                await conn.execute(
                    """
                    UPDATE tenants
                    SET bullhorn_credentials_ciphertext = $1,
                        bullhorn_credentials_version    = $2,
                        bullhorn_credentials_updated_at = now(),
                        bullhorn_config                 = $3::jsonb
                    WHERE id = $4
                    """,
                    ciphertext,
                    current_key_version(),
                    json.dumps(cleaned_cfg),
                    row["id"],
                )
                updated += 1

        print(f"Done: {updated} tenant(s) {'updated' if not args.dry_run else '(dry-run)'}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
