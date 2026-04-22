"""
AI content generation engine for StaffingAgent.ai marketing.
Uses Claude to generate LinkedIn posts, email sequences, and blog outlines
tailored to specific buyer personas and topics.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.marketing.personas import get_persona

_TEMPLATES_DIR = Path(__file__).parent / "templates"

TOPICS: dict[str, str] = {
    "command_center": "The StaffingAgent Command Center: one dashboard for real-time visibility into placements, timesheets, payroll, billing, and invoices — embedded in Bullhorn",
    "missing_timesheets": "Missing timesheets as the #1 source of revenue leakage in staffing — how a single dashboard surfaces 142 missing timesheets instantly with one-click mass reminders",
    "risk_alerts": "Real-time risk detection across 7 categories (rate flags, hours anomalies, wage compliance, markup analysis) — caught automatically, not at audit",
    "manual_reports": "The hidden cost of manual report-building in pay/bill operations — 8-12 hours/week per person spent in Excel instead of resolving issues",
    "middle_office": "The staffing middle office is the last untouched automation frontier — why operational visibility is the first step before AI agents",
    "vms": "VMS reconciliation errors and revenue leakage in staffing firms",
    "time_anomaly": "Timesheet anomalies, ghost shifts, and overtime fraud in staffing",
    "invoice": "Invoice matching, billing errors, and the $440K sitting unprocessed that nobody can see",
    "compliance": "Compliance and credentialing risk in staffing firms — wage violations, rate mismatches, and markup analysis",
    "collections": "Collections strategy, DSO, and AR optimization — 58 invoices worth $298K undelivered to customers",
    "payment": "Payment prediction, cash flow forecasting, and DSO management",
    "ai_readiness": "How staffing firms should evaluate AI readiness — start with visibility, then layer agents",
    "bullhorn_migration": "Why Bullhorn One migration is the perfect time to add operational intelligence — the Command Center as your safety net during transition",
    "roi": "ROI of the Command Center: $5K/month vs. $150K-$300K/year in labor savings, plus recovered revenue from missing timesheets and billing errors",
    "dashboard_vs_agents": "Dashboard first, agents second: why the smartest staffing firms start with operational visibility before deploying AI automation",
    "weekly_mix": "Mix of Command Center and middle-office topics for staffing executives (rotate across visibility, risk, missing timesheets, and ROI)",
}


def _load_template(name: str) -> str:
    path = _TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def _invoke(system: str, user_prompt: str, max_tokens: int = 4096) -> str:
    """Call Claude and return text response."""
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY must be set")

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if resp.content and resp.content[0].type == "text":
        return resp.content[0].text
    return ""


def generate_linkedin_posts(
    persona_key: str,
    topic_key: str,
    count: int = 5,
) -> str:
    persona = get_persona(persona_key)
    topic = TOPICS.get(topic_key, topic_key)
    template = _load_template("linkedin_post.txt")

    system = template.format(
        persona_title=persona.title,
        topic=topic,
        pain_points="\n".join(f"- {p}" for p in persona.pain_points),
        value_drivers="\n".join(f"- {v}" for v in persona.value_drivers),
        count=count,
    )

    return _invoke(system, f"Generate {count} LinkedIn posts now.")


def generate_email_sequence(
    persona_key: str,
    sequence_type: str = "post_assessment",
    email_count: int = 3,
    duration: str = "2 weeks",
) -> str:
    persona = get_persona(persona_key)
    template = _load_template("email_sequence.txt")

    sequence_configs: dict[str, dict[str, Any]] = {
        "post_assessment": {
            "sequence_type": "Post-Assessment Nurture",
            "sequence_context": (
                "The prospect just completed the AI Readiness Assessment on "
                "staffingagent.ai. They scored between 2-5 out of 5, indicating "
                "they have some readiness but may need foundation work. Goal: "
                "move them to a discovery call."
            ),
            "email_count": 3,
            "duration": "2 weeks",
        },
        "post_demo": {
            "sequence_type": "Post-Demo Follow-up",
            "sequence_context": (
                "The prospect tried one of the live agent demos on "
                "staffingagent.ai (VMS reconciliation, time anomaly, invoice "
                "matching, or collections). They provided their email to unlock "
                "file upload. Goal: convert demo interest into a discovery call."
            ),
            "email_count": 2,
            "duration": "1 week",
        },
        "cold_outbound": {
            "sequence_type": "Cold Outbound Introduction",
            "sequence_context": (
                "Cold outreach to a staffing firm executive who has not "
                "interacted with the website. Goal: earn a first meeting by "
                "leading with value and industry insight."
            ),
            "email_count": 3,
            "duration": "3 weeks",
        },
    }

    config = sequence_configs.get(sequence_type, {
        "sequence_type": sequence_type,
        "sequence_context": "General nurture sequence.",
        "email_count": email_count,
        "duration": duration,
    })

    extra = ""
    if config["email_count"] > 3:
        extra = (
            "- Email 4: Direct value proposition. 'Here's exactly what this would "
            "look like for a firm your size.'\n"
            "- Email 5: Final follow-up. Respect their time, leave the door open."
        )

    system = template.format(
        persona_title=persona.title,
        sequence_type=config["sequence_type"],
        sequence_context=config["sequence_context"],
        email_count=config["email_count"],
        duration=config["duration"],
        extra_emails=extra,
        pain_points="\n".join(f"- {p}" for p in persona.pain_points),
        value_drivers="\n".join(f"- {v}" for v in persona.value_drivers),
    )

    return _invoke(system, "Generate the email sequence now.")


def generate_blog_outline(
    persona_key: str,
    topic_key: str,
    keyword: str = "",
    word_count: int = 1200,
) -> str:
    persona = get_persona(persona_key)
    topic = TOPICS.get(topic_key, topic_key)
    template = _load_template("blog_outline.txt")

    if not keyword:
        keyword = topic_key.replace("_", " ") + " staffing AI"

    system = template.format(
        persona_title=persona.title,
        topic=topic,
        keyword=keyword,
        word_count=word_count,
    )

    return _invoke(system, "Generate the blog outline now.")
