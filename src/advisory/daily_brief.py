"""
CEO Daily Brief Engine — StaffingAgent.ai

Generates a tactical daily brief using Claude (CoS + CFO perspective).
Output is a structured dict delivered via email (Resend) and optionally synced to Notion.

Entrypoint: python -m src.advisory.daily_brief

The daily brief is intentionally different from the weekly advisory board:
  - Weekly board: strategic, 5 personas, deep analysis
  - Daily brief: tactical, actionable, 3 priorities, 5-minute read

Decision filter hardwired into every prompt:
  1. Accelerate a signed customer?
  2. Improve Assess->Transform conversion?
  3. Increase GP$ without adding FTE?
  4. Reduce a HIGH-severity risk?

Notion sync is optional — runs automatically if NOTION_API_KEY is set.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

import anthropic

from .email_sender import send_daily_brief
from .hubspot_pulse import fetch_hubspot_pulse
from .notion_sync import sync_to_notion
from .personas import load_master_context
from .state import get_report_date, load_current_state

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1800

DAILY_BRIEF_SYSTEM_PROMPT = """You are the integrated CEO Operating System for StaffingAgent.ai.
You combine the Chief of Staff (tactical execution) and CFO (financial discipline) perspectives
into a single daily brief for Chris Scowden, CEO.

Your output must be a JSON object with exactly this structure:
{
  "priorities": [
    "Specific action #1 — who, what, by when",
    "Specific action #2 — who, what, by when",
    "Specific action #3 — who, what, by when"
  ],
  "pipeline": {
    "company": "Company name",
    "stage": "Current stage",
    "next_action": "Specific next action",
    "days_since_contact": "X"
  },
  "legal": {
    "complete": 3,
    "total": 9,
    "next_overdue": "Description of next overdue item or 'All current'"
  },
  "key_metric": {
    "value": "$0",
    "label": "Current MRR",
    "context": "One sentence of context"
  },
  "open_tasks": [
    {
      "name": "Task description",
      "category": "Pipeline",
      "priority": "High",
      "source": "Daily Brief"
    }
  ],
  "full_analysis": "2-3 paragraphs of deeper context for the Notion archive"
}

Categories for tasks: Pipeline, Legal, Product, Hiring, Finance, Strategy
Priorities for tasks: High, Med, Low

Rules:
- Priorities must be specific and actionable. Never vague ("work on pipeline").
  Always name the company, person, or document. Example: "Email Cortney re: GHR demo date — 5-min task"
- The hot deal in pipeline should be whichever company is closest to signing, not the largest.
- Legal complete/total counts from the 30-day execution checklist in the master context.
- Key metric should reflect the single most important number this week (pre-revenue = MRR $0, 
  but also show pipeline value or legal progress as the metric if more meaningful).
- Open tasks should be net-new actionable items, not repeats of the priorities.
- full_analysis is the "why" behind the priorities — 2-3 paragraphs, Notion archive quality.

Apply the decision filter to every priority:
  1. Does it accelerate a signed customer? (highest priority)
  2. Does it improve Assess->Transform conversion mechanics?
  3. Does it increase GP$ without adding FTE?
  4. Does it reduce a HIGH-severity risk?

Output ONLY the JSON object. No preamble, no explanation, no markdown code fences."""


def _extract_json(text: str) -> dict:
    """Extract JSON from Claude's response, handling any extra text."""
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Return a safe fallback so the system doesn't crash
    print("  Warning: Could not parse JSON from Claude response. Using fallback brief.")
    return {
        "priorities": [
            "Check current-state.md and update pipeline stages",
            "Review legal checklist — confirm attorney is engaged",
            "Send demo scheduling email to GHR (Cortney/Jane)",
        ],
        "pipeline": {
            "company": "GHR",
            "stage": "Demo Scheduled",
            "next_action": "Confirm demo date with Cortney",
            "days_since_contact": "Unknown",
        },
        "legal": {"complete": 0, "total": 9, "next_overdue": "Engage Texas attorney"},
        "key_metric": {"value": "$0", "label": "Current MRR", "context": "Pre-revenue — first customer is the only metric that matters"},
        "open_tasks": [
            {"name": "Update current-state.md with latest pipeline status", "category": "Strategy", "priority": "High", "source": "Daily Brief"},
            {"name": "Confirm Command Center demo date with GHR", "category": "Pipeline", "priority": "High", "source": "Daily Brief"},
        ],
        "full_analysis": text[:1000] if text else "Analysis unavailable — check GitHub Actions logs.",
    }


def generate_brief(
    master_context: str,
    current_state: str,
    hubspot_pulse: str,
    report_date: str,
) -> dict:
    """Call Claude to generate the structured daily brief."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)

    hubspot_section = ""
    if hubspot_pulse:
        hubspot_section = f"""
--- HUBSPOT CRM DATA (live from API) ---
{hubspot_pulse}
Use this to cross-check pipeline in current-state. HubSpot is source of truth for deals and recent contacts.
"""

    user_prompt = f"""Today is {report_date}.

Generate today's CEO Daily Brief for Chris Scowden, CEO of StaffingAgent.ai.

--- MASTER BUSINESS CONTEXT ---
{master_context}

--- THIS WEEK'S CURRENT STATE ---
{current_state}
{hubspot_section}
Based on everything above, generate the JSON daily brief.
Focus on what Chris should do TODAY — not this week, not eventually. TODAY.
The #1 priority should always be the action that most directly accelerates a signed customer.
When HubSpot data is present, prefer it for pipeline hot deal and next actions."""

    print("  Calling Claude for daily brief generation...", flush=True)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=DAILY_BRIEF_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text
    brief = _extract_json(raw_text)
    brief["date"] = report_date
    return brief


def main() -> None:
    """Main entrypoint: generate brief (with HubSpot pulse), send email."""
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"

    print("StaffingAgent CEO Operating System — Daily Brief")
    print(f"Run time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    if dry_run:
        print("MODE: DRY RUN — email will not be sent")
    print("=" * 60)

    # Load inputs
    print("\nLoading business context...")
    try:
        master_context = load_master_context()
        current_state = load_current_state()
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    report_date = get_report_date()

    # Fetch HubSpot pulse (optional — graceful if token not set)
    print("Fetching HubSpot pulse...")
    hubspot_pulse = fetch_hubspot_pulse()
    if hubspot_pulse:
        print("  HubSpot data loaded (pipeline + recent contacts)")
    else:
        print("  HubSpot skipped (HUBSPOT_ACCESS_TOKEN not set or API error)")

    print(f"Generating daily brief for {report_date}...")

    # Generate the brief
    try:
        brief = generate_brief(master_context, current_state, hubspot_pulse, report_date)
        print(f"  Brief generated: {len(brief.get('priorities', []))} priorities, "
              f"{len(brief.get('open_tasks', []))} tasks")
    except Exception as e:
        print(f"ERROR generating brief: {e}", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN — BRIEF CONTENTS:")
        print("=" * 60)
        print(f"\nDate: {brief['date']}")
        print("\nTOP 3 PRIORITIES:")
        for i, p in enumerate(brief.get("priorities", []), 1):
            print(f"  {i}. {p}")
        print(f"\nPIPELINE: {brief.get('pipeline', {}).get('company')} — {brief.get('pipeline', {}).get('stage')}")
        print(f"LEGAL: {brief.get('legal', {}).get('complete')}/{brief.get('legal', {}).get('total')} complete")
        metric = brief.get("key_metric", {})
        print(f"KEY METRIC: {metric.get('value')} — {metric.get('label')}")
        print(f"\nOPEN TASKS ({len(brief.get('open_tasks', []))}):")
        for t in brief.get("open_tasks", []):
            print(f"  [{t.get('priority')}] {t.get('name')}")
        notion_status = "enabled" if os.environ.get("NOTION_API_KEY") else "skipped (NOTION_API_KEY not set)"
        print(f"\nNotion sync: {notion_status}")
        print("Dry run complete. No email sent.")
        return

    # Send email
    print("Sending email via Resend...")
    try:
        send_daily_brief(brief)
        print(f"Daily brief delivered for {report_date}")
    except Exception as e:
        print(f"ERROR sending email: {e}", file=sys.stderr)
        # Print brief to logs so it's not completely lost
        print("\nBRIEF CONTENT (email failed):")
        for i, p in enumerate(brief.get("priorities", []), 1):
            print(f"  {i}. {p}")
        sys.exit(1)

    # Sync to Notion (optional — only runs if NOTION_API_KEY is set)
    if os.environ.get("NOTION_API_KEY"):
        try:
            brief_url, tasks_url = sync_to_notion(brief)
            if brief_url:
                print(f"  Notion brief archived: {brief_url}")
            if tasks_url:
                print(f"  Notion task board updated: {tasks_url}")
        except Exception as e:
            # Notion failure must never block email delivery
            print(f"  Warning: Notion sync failed (non-fatal): {e}", file=sys.stderr)
    else:
        print("  Notion sync skipped (NOTION_API_KEY not set — see docs/notion-setup-guide.md)")


if __name__ == "__main__":
    main()
