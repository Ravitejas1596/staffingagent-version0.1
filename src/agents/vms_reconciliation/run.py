"""
CLI runner for the VMS Reconciliation agent.
Usage:
  python -m src.agents.vms_reconciliation.run
  python -m src.agents.vms_reconciliation.run path/to/state.json
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

from src.agents.vms_reconciliation import get_graph


def _default_state() -> dict[str, Any]:
    return {
        "tenant_id": os.environ.get("STAFFINGAGENT_TENANT", "default"),
        "vms_records": [
            {
                "id": "v1",
                "facility": "Facility A",
                "candidate": "John Doe",
                "hours": 40,
                "date": "2026-03-01",
            },
            {
                "id": "v2",
                "facility": "Facility B",
                "candidate": "Jane Smith",
                "hours": 32,
                "date": "2026-03-01",
            },
        ],
        "ats_records": [
            {
                "id": "a1",
                "placement_id": "P1",
                "candidate": "John Doe",
                "hours": 40,
                "job": "J1",
            },
            {
                "id": "a2",
                "placement_id": "P2",
                "candidate": "Jane Smith",
                "hours": 32,
                "job": "J2",
            },
        ],
    }


def main() -> None:
    load_dotenv()
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            initial = json.load(f)
    else:
        initial = _default_state()

    graph = get_graph()
    result = graph.invoke(initial)
    print(json.dumps(result.get("result") or result, indent=2, default=str))
    if result.get("token_usage"):
        print("\nToken usage:", result["token_usage"])


if __name__ == "__main__":
    main()
