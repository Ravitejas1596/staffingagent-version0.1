"""
Run connectivity checks against configured nBrain and Bullhorn integrations.

Usage:
  python scripts/check_integrations.py --tenant default --check all
  python scripts/check_integrations.py --check nbrain --query "open invoices"
  python scripts/check_integrations.py --check bullhorn --bullhorn-path "/query/Placement"
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from src.api.gateway import bullhorn_rest, nbrain_query


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


async def _run_nbrain_check(tenant: str, query: str, limit: int) -> CheckResult:
    try:
        rows = await nbrain_query(tenant, query, limit=limit)
        return CheckResult("nbrain", True, f"received {len(rows)} rows")
    except Exception as exc:  # pragma: no cover - direct runtime diagnostics
        return CheckResult("nbrain", False, str(exc))


async def _run_bullhorn_check(
    tenant: str,
    path: str,
    params: dict[str, Any] | None = None,
) -> CheckResult:
    try:
        payload = await bullhorn_rest(tenant, "GET", path, params=params)
        keys = list(payload.keys())[:10] if isinstance(payload, dict) else []
        return CheckResult("bullhorn", True, f"response keys={keys}")
    except Exception as exc:  # pragma: no cover - direct runtime diagnostics
        return CheckResult("bullhorn", False, str(exc))


def _print_result(result: CheckResult) -> None:
    status = "OK" if result.ok else "FAIL"
    print(f"[{status}] {result.name}: {result.detail}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check external integration connectivity")
    parser.add_argument("--tenant", default="default", help="Tenant id for requests")
    parser.add_argument(
        "--check",
        choices=["all", "nbrain", "bullhorn"],
        default="all",
        help="Which integration checks to run",
    )
    parser.add_argument("--query", default="open invoices", help="nBrain test query string")
    parser.add_argument("--limit", type=int, default=3, help="nBrain result limit")
    parser.add_argument(
        "--bullhorn-path",
        default="/query/Placement",
        help="Bullhorn relative path for read-only connectivity test",
    )
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()
    load_dotenv()

    checks: list[CheckResult] = []
    if args.check in ("all", "nbrain"):
        checks.append(await _run_nbrain_check(args.tenant, args.query, args.limit))
    if args.check in ("all", "bullhorn"):
        checks.append(await _run_bullhorn_check(args.tenant, args.bullhorn_path))

    for result in checks:
        _print_result(result)

    if all(result.ok for result in checks):
        print("\nIntegration checks passed.")
        return 0

    print("\nOne or more integration checks failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
