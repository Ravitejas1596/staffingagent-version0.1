"""
Run VMS Reconciliation agent with sample or injected state.
Usage: python scripts/run_vms_reconciliation.py
Set ANTHROPIC_API_KEY. Optional: pass JSON file path for initial state.
"""
import json
import os
import sys

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.agents.vms_reconciliation import get_graph  # noqa: E402


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            initial = json.load(f)
    else:
        initial = {
            "tenant_id": os.environ.get("STAFFINGAGENT_TENANT", "default"),
            "vms_records": [
                {"id": "v1", "facility": "Facility A", "candidate": "John Doe", "hours": 40, "date": "2026-03-01"},
                {"id": "v2", "facility": "Facility B", "candidate": "Jane Smith", "hours": 32, "date": "2026-03-01"},
            ],
            "ats_records": [
                {"id": "a1", "placement_id": "P1", "candidate": "John Doe", "hours": 40, "job": "J1"},
                {"id": "a2", "placement_id": "P2", "candidate": "Jane Smith", "hours": 32, "job": "J2"},
            ],
        }
    graph = get_graph()
    result = graph.invoke(initial)
    print(json.dumps(result.get("result") or result, indent=2, default=str))
    if result.get("token_usage"):
        print("\nToken usage:", result["token_usage"])


if __name__ == "__main__":
    main()
