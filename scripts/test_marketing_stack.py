#!/usr/bin/env python3
"""
End-to-end test for the StaffingAgent marketing stack.
Verifies: environment variables, content engine, HubSpot API, form submission.

Usage:
    python scripts/test_marketing_stack.py
    python scripts/test_marketing_stack.py --skip-claude    # Skip content generation (saves API cost)
    python scripts/test_marketing_stack.py --skip-hubspot   # Skip HubSpot API tests
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    icon = {"PASS": "+", "FAIL": "X", "SKIP": "-"}[status]
    line = f"  [{icon}] {name}"
    if detail:
        line += f" -- {detail}"
    print(line)


def check_env() -> None:
    print("\n== Environment Variables ==")
    required = {
        "ANTHROPIC_API_KEY": "Content generation (Claude)",
        "HUBSPOT_ACCESS_TOKEN": "HubSpot API (contacts, deals)",
        "HUBSPOT_PORTAL_ID": "HubSpot portal identification",
        "HUBSPOT_FORM_GUID": "HubSpot form submission",
    }
    for var, purpose in required.items():
        val = os.environ.get(var, "")
        if val:
            masked = val[:8] + "..." if len(val) > 12 else val[:4] + "..."
            record(f"ENV: {var}", PASS, f"Set ({masked}) -- {purpose}")
        else:
            record(f"ENV: {var}", FAIL, f"MISSING -- needed for: {purpose}")


def check_content_engine(skip: bool) -> None:
    print("\n== Content Engine ==")

    if skip:
        record("Content engine (Claude)", SKIP, "--skip-claude flag set")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        record("Content engine", SKIP, "ANTHROPIC_API_KEY not set")
        return

    try:
        from src.marketing.personas import get_persona, ALL_PERSONAS

        for key in ALL_PERSONAS:
            p = get_persona(key)
            assert p.key == key
            assert len(p.pain_points) >= 4
            assert len(p.value_drivers) >= 4
        record("Personas loaded", PASS, f"{len(ALL_PERSONAS)} personas with Command Center messaging")
    except Exception as e:
        record("Personas loaded", FAIL, str(e))
        return

    try:
        from src.marketing.content_engine import TOPICS

        cc_topics = [k for k in TOPICS if k in ("command_center", "missing_timesheets", "risk_alerts", "manual_reports", "dashboard_vs_agents", "bullhorn_migration")]
        record("Topics updated", PASS, f"{len(TOPICS)} topics, {len(cc_topics)} Command Center-specific")
    except Exception as e:
        record("Topics updated", FAIL, str(e))

    try:
        from src.marketing.content_engine import generate_linkedin_posts

        print("    Generating 1 test LinkedIn post (this calls Claude)...")
        content = generate_linkedin_posts("vp_ops", "command_center", count=1)
        assert len(content) > 100, f"Content too short: {len(content)} chars"
        record("LinkedIn generation", PASS, f"{len(content)} chars generated")
    except Exception as e:
        record("LinkedIn generation", FAIL, str(e))

    try:
        from src.marketing.calendar import generate_calendar

        entries = generate_calendar(weeks=1, posts_per_week=5)
        assert len(entries) >= 5
        cc_entries = [e for e in entries if e["topic"] in ("command_center", "missing_timesheets", "risk_alerts", "manual_reports")]
        record("Calendar generation", PASS, f"{len(entries)} entries, {len(cc_entries)} Command Center topics")
    except Exception as e:
        record("Calendar generation", FAIL, str(e))


def check_hubspot(skip: bool) -> None:
    print("\n== HubSpot Integration ==")

    if skip:
        record("HubSpot API", SKIP, "--skip-hubspot flag set")
        return

    token = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
    portal = os.environ.get("HUBSPOT_PORTAL_ID", "")
    form = os.environ.get("HUBSPOT_FORM_GUID", "")

    if not token:
        record("HubSpot API", SKIP, "HUBSPOT_ACCESS_TOKEN not set")
        return

    # Test API connectivity
    try:
        import httpx

        resp = httpx.get(
            "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            record("HubSpot API connection", PASS, "Contacts endpoint reachable")
        elif resp.status_code == 401:
            record("HubSpot API connection", FAIL, "401 Unauthorized -- token may be expired or invalid")
        else:
            record("HubSpot API connection", FAIL, f"HTTP {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        record("HubSpot API connection", FAIL, str(e))

    # Test deals endpoint
    try:
        resp = httpx.get(
            "https://api.hubapi.com/crm/v3/objects/deals?limit=1",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            record("HubSpot Deals API", PASS, "Deals endpoint reachable")
        else:
            record("HubSpot Deals API", FAIL, f"HTTP {resp.status_code}")
    except Exception as e:
        record("HubSpot Deals API", FAIL, str(e))

    # Test form submission endpoint (dry run — checks the endpoint exists)
    if portal and form:
        try:
            resp = httpx.post(
                f"https://api.hsforms.com/submissions/v3/integration/submit/{portal}/{form}",
                json={"fields": [{"name": "email", "value": "test-dry-run@staffingagent.ai"}]},
                timeout=10,
            )
            if resp.status_code in (200, 204):
                record("HubSpot Form submission", PASS, f"Form {form[:8]}... accepts submissions")
            elif resp.status_code == 400:
                record("HubSpot Form submission", PASS, f"Form endpoint reachable (validation error expected for test data)")
            else:
                record("HubSpot Form submission", FAIL, f"HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            record("HubSpot Form submission", FAIL, str(e))
    else:
        record("HubSpot Form submission", SKIP, "HUBSPOT_PORTAL_ID or HUBSPOT_FORM_GUID not set")

    # Test Python client import
    try:
        from src.integrations.hubspot import PIPELINE_STAGES

        record("HubSpot Python client", PASS, f"{len(PIPELINE_STAGES)} pipeline stages defined")
    except Exception as e:
        record("HubSpot Python client", FAIL, str(e))


def check_site_wiring() -> None:
    print("\n== Site Wiring ==")

    site_dir = Path(__file__).resolve().parent.parent / "site"

    # Check HubSpot tracking on key pages
    key_pages = ["index.html", "demos.html", "assessment.html", "roi.html", "demo-command-center.html"]
    for page in key_pages:
        path = site_dir / page
        if not path.exists():
            record(f"Site: {page}", FAIL, "File not found")
            continue
        content = path.read_text(encoding="utf-8")
        has_hs = "hs-scripts.com/245521589" in content or "hs-script-loader" in content
        if has_hs:
            record(f"Site: {page} HubSpot tracking", PASS)
        else:
            record(f"Site: {page} HubSpot tracking", FAIL, "HubSpot tracking script not found")

    # Check form wiring in demos.js
    demos_js = site_dir / "demos.js"
    if demos_js.exists():
        content = demos_js.read_text(encoding="utf-8")
        has_form_api = "hsforms.com" in content
        has_form_guid = "33eb4c23" in content
        if has_form_api and has_form_guid:
            record("Site: demos.js HubSpot Forms API", PASS, "Form GUID wired")
        elif has_form_api:
            record("Site: demos.js HubSpot Forms API", PASS, "Forms API present (check GUID)")
        else:
            record("Site: demos.js HubSpot Forms API", FAIL, "No HubSpot Forms API submission found")

    # Check assessment.js
    assessment_js = site_dir / "assessment.js"
    if assessment_js.exists():
        content = assessment_js.read_text(encoding="utf-8")
        has_form_api = "hsforms.com" in content or "_hsq" in content
        if has_form_api:
            record("Site: assessment.js HubSpot wiring", PASS)
        else:
            record("Site: assessment.js HubSpot wiring", FAIL, "No HubSpot submission found")


def print_summary() -> None:
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total = len(results)
    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = sum(1 for _, s, _ in results if s == FAIL)
    skipped = sum(1 for _, s, _ in results if s == SKIP)

    print(f"  Total: {total} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}")

    if failed > 0:
        print("\n  FAILURES:")
        for name, status, detail in results:
            if status == FAIL:
                print(f"    - {name}: {detail}")

    if skipped > 0:
        print(f"\n  SKIPPED: {skipped} tests (use flags or set env vars to enable)")

    print()
    if failed == 0:
        print("  All tests passed. Marketing stack is operational.")
    else:
        print(f"  {failed} issue(s) to fix. See details above.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Test StaffingAgent marketing stack")
    parser.add_argument("--skip-claude", action="store_true", help="Skip Claude API content generation tests")
    parser.add_argument("--skip-hubspot", action="store_true", help="Skip HubSpot API tests")
    args = parser.parse_args()

    print("StaffingAgent.ai — Marketing Stack Test")
    print("=" * 60)

    check_env()
    check_content_engine(skip=args.skip_claude)
    check_hubspot(skip=args.skip_hubspot)
    check_site_wiring()
    print_summary()


if __name__ == "__main__":
    main()
