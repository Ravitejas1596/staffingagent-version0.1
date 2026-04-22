"""
Content calendar generator for StaffingAgent.ai marketing.
Produces a 4-week plan mixing educational, social proof, and CTA content
across LinkedIn and email channels.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from src.marketing.content_engine import TOPICS
from src.marketing.personas import ALL_PERSONAS

CONTENT_MIX = {
    "educational": 0.70,
    "social_proof": 0.20,
    "direct_cta": 0.10,
}

EDUCATIONAL_TOPICS = [
    "command_center", "missing_timesheets", "risk_alerts", "manual_reports",
    "middle_office", "invoice", "compliance", "dashboard_vs_agents",
    "bullhorn_migration", "ai_readiness",
]

SOCIAL_PROOF_ANGLES = [
    "ROI math: $5K/month vs. $150K-$300K/year in labor savings plus recovered revenue",
    "100% ROI guarantee — measured quarterly across 6 dimensions",
    "142 missing timesheets surfaced in seconds — what your team spends hours chasing",
    "From 8-12 hours/week of manual reporting to real-time visibility in Bullhorn",
    "$298K in invoices sitting undelivered — money billed but customers don't know they owe it",
]

CTA_HOOKS = [
    "See the Command Center live demo (staffingagent.ai/demo-command-center.html)",
    "AI Readiness Assessment (staffingagent.ai/assessment.html)",
    "ROI Calculator (staffingagent.ai/roi.html)",
    "Book a Discovery Call — see it with your Bullhorn data",
]


def generate_calendar(
    weeks: int = 4,
    posts_per_week: int = 5,
    start_date: date | None = None,
) -> list[dict[str, Any]]:
    """
    Returns a list of content calendar entries.
    Each entry: {date, day_of_week, channel, content_type, topic, persona, notes}
    """
    start = start_date or date.today()
    if start.weekday() != 0:
        start = start + timedelta(days=(7 - start.weekday()) % 7)

    persona_keys = list(ALL_PERSONAS.keys())
    entries: list[dict[str, Any]] = []

    for week in range(weeks):
        week_start = start + timedelta(weeks=week)
        post_days = [0, 1, 2, 3, 4]  # Mon-Fri

        for i, day_offset in enumerate(post_days[:posts_per_week]):
            post_date = week_start + timedelta(days=day_offset)

            total_idx = week * posts_per_week + i
            edu_count = round(posts_per_week * CONTENT_MIX["educational"])
            proof_count = round(posts_per_week * CONTENT_MIX["social_proof"])

            if i < edu_count:
                content_type = "educational"
                topic = EDUCATIONAL_TOPICS[total_idx % len(EDUCATIONAL_TOPICS)]
                notes = f"Deep-dive on {TOPICS.get(topic, topic)}"
            elif i < edu_count + proof_count:
                content_type = "social_proof"
                topic = "roi"
                notes = SOCIAL_PROOF_ANGLES[total_idx % len(SOCIAL_PROOF_ANGLES)]
            else:
                content_type = "direct_cta"
                topic = "weekly_mix"
                notes = CTA_HOOKS[total_idx % len(CTA_HOOKS)]

            persona = persona_keys[total_idx % len(persona_keys)]

            entries.append({
                "date": post_date.isoformat(),
                "day_of_week": post_date.strftime("%A"),
                "week": week + 1,
                "channel": "LinkedIn",
                "content_type": content_type,
                "topic": topic,
                "persona": persona,
                "notes": notes,
            })

        if week % 2 == 0:
            entries.append({
                "date": (week_start + timedelta(days=1)).isoformat(),
                "day_of_week": "Tuesday",
                "week": week + 1,
                "channel": "Email",
                "content_type": "nurture_sequence",
                "topic": "post_assessment" if week == 0 else "cold_outbound",
                "persona": persona_keys[week % len(persona_keys)],
                "notes": "Trigger-based sequence for new leads" if week == 0
                         else "Cold outbound batch",
            })

    return entries


def format_calendar_text(entries: list[dict[str, Any]]) -> str:
    lines = ["STAFFINGAGENT.AI — CONTENT CALENDAR", "=" * 50, ""]
    current_week = 0

    for entry in entries:
        if entry["week"] != current_week:
            current_week = entry["week"]
            lines.append(f"\n--- WEEK {current_week} ---\n")

        lines.append(
            f"  {entry['date']} ({entry['day_of_week']}) | "
            f"{entry['channel']:8s} | {entry['content_type']:14s} | "
            f"Persona: {entry['persona']:7s} | {entry['notes']}"
        )

    return "\n".join(lines)


def format_calendar_json(entries: list[dict[str, Any]]) -> str:
    return json.dumps(entries, indent=2)
