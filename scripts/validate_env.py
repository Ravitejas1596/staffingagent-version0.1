"""
Validate local environment for StaffingAgent development.

Usage:
  python scripts/validate_env.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv


REQUIRED = ["ANTHROPIC_API_KEY"]
OPTIONAL = [
    "NBRAIN_API_URL",
    "NBRAIN_API_KEY",
    "NBRAIN_QUERY_PATH",
    "NBRAIN_RESULTS_KEY",
    "BULLHORN_REST_URL",
    "BULLHORN_TOKEN_URL",
    "BULLHORN_CLIENT_ID",
    "BULLHORN_CLIENT_SECRET",
    "BULLHORN_BEARER_TOKEN",
    "ATS_RESULTS_KEY",
]


def _is_set(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def main() -> int:
    load_dotenv()
    print("StaffingAgent environment validation\n")

    missing_required = [name for name in REQUIRED if not _is_set(name)]
    for name in REQUIRED:
        print(f"[{'OK' if _is_set(name) else 'MISSING'}] required: {name}")

    print()
    for name in OPTIONAL:
        print(f"[{'SET' if _is_set(name) else 'UNSET'}] optional: {name}")

    print()
    if _is_set("BULLHORN_BEARER_TOKEN"):
        print("[INFO] Bullhorn auth mode: static bearer token")
    elif _is_set("BULLHORN_TOKEN_URL") and _is_set("BULLHORN_CLIENT_ID") and _is_set(
        "BULLHORN_CLIENT_SECRET"
    ):
        print("[INFO] Bullhorn auth mode: OAuth client credentials")
    else:
        print("[INFO] Bullhorn auth mode: not fully configured")

    if missing_required:
        print("\nValidation failed: required environment variables are missing.")
        return 1

    print("\nValidation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
