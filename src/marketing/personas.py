"""
Target buyer personas for StaffingAgent.ai content generation.
Each persona captures the pain points, language, and objections
that the AI content engine uses to tailor messaging.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    key: str
    title: str
    titles_variations: list[str]
    pain_points: list[str]
    language_style: str
    objections: list[str]
    value_drivers: list[str]
    industry_context: str


VP_OPS = Persona(
    key="vp_ops",
    title="VP of Operations",
    titles_variations=[
        "VP Operations",
        "SVP Operations",
        "Director of Operations",
        "Chief Operating Officer",
        "Head of Middle Office",
        "Director of Pay/Bill",
    ],
    pain_points=[
        "Pay/bill teams spend 8-12 hours/week per person pulling manual reports just to see where things stand",
        "Missing timesheets become unbilled revenue — 2-5% revenue leakage industry average",
        "No single view across placements, timesheets, payroll, billing, and invoices",
        "Risk alerts (rate mismatches, compliance gaps, hours anomalies) discovered at audit, not in real time",
        "Can't scale operations without proportionally scaling headcount",
        "Manual report-building in Excel means problems are found at payroll cutoff, not when they happen",
    ],
    language_style=(
        "Operational, metric-driven. Talks in headcount, hours saved, error rates, "
        "and missing timesheets. Values reliability and proof points over vision. "
        "Skeptical of 'AI hype' — wants to see the dashboard, not the algorithm. "
        "Cares about mass actions, audit trails, and team accountability."
    ),
    objections=[
        "We already have Power BI / custom reports for this",
        "AI will disrupt our team",
        "Our Bullhorn data isn't clean enough",
        "We tried automation before and it didn't stick",
        "We're in the middle of a Bullhorn One migration",
    ],
    value_drivers=[
        "8-12 hours saved per week per team member — replace manual report-building",
        "Real-time visibility into all 5 entity panels (Placements, T&E, Payroll, Billing, Invoices)",
        "142 missing timesheets surfaced instantly with one-click mass reminders",
        "7 risk categories monitored automatically — rate flags, hours flags, wage compliance, markup analysis",
        "One-click mass actions: send reminders, update statuses, escalate, export",
        "100% ROI guarantee backed by quarterly measurement",
    ],
    industry_context=(
        "Mid-to-large staffing firms ($100M-$1B+) with 500+ active contractors. "
        "Runs Bullhorn One. Uses 1-3 VMS platforms (Fieldglass, Beeline, "
        "VectorVMS, Magnit). Pay/bill team of 5-20 people handling timesheets, "
        "payroll processing, billing, invoicing, and collections. "
        "The Command Center dashboard embeds directly in Bullhorn."
    ),
)

CFO = Persona(
    key="cfo",
    title="CFO / VP Finance",
    titles_variations=[
        "Chief Financial Officer",
        "VP Finance",
        "SVP Finance",
        "Controller",
        "Director of Finance",
    ],
    pain_points=[
        "DSO keeps climbing — 58 invoices worth $298K sitting undelivered to customers right now",
        "Revenue leakage from missing timesheets: 142 missing in a single pay period = $284K at risk",
        "$238K in payable charges stuck unprocessed — money in limbo with no visibility",
        "$440K in billable charges not yet invoiced — cash delayed because nobody knew it was ready",
        "Billing errors and rate mismatches compound into write-offs that hit the P&L",
        "No way to see the full financial picture across payroll, billing, and invoices in one view",
    ],
    language_style=(
        "Financial, ROI-focused. Speaks in DSO, GP margin, write-offs, and payback period. "
        "Wants a business case with numbers, not a technology pitch. "
        "Evaluates everything through OpEx lens — $5K/month vs. measurable value. "
        "Responds to 'dollars stuck in the pipeline' framing."
    ),
    objections=[
        "What's the payback period?",
        "How do you guarantee ROI?",
        "$5K/month is a lot for a dashboard",
        "Our current tools should be doing this already",
        "We need to see it with our data first",
    ],
    value_drivers=[
        "Full financial visibility: every dollar tracked from placement through invoice delivery",
        "Risk alerts catch rate mismatches and billing errors before they become write-offs",
        "$150K-$300K/year saved in labor from eliminating manual report-building",
        "100% ROI guarantee — measured quarterly across 6 dimensions",
        "Implementation included, live in 3-5 business days",
    ],
    industry_context=(
        "Staffing firm finance leaders managing $100M-$1B+ in annual revenue. "
        "Responsible for AR aging, DSO, GP margin, and cash flow forecasting. "
        "The Command Center shows them real-time financial status across all "
        "5 entity panels — no more waiting for weekly Excel reports."
    ),
)

CTO = Persona(
    key="cto",
    title="CTO / CIO",
    titles_variations=[
        "Chief Technology Officer",
        "Chief Information Officer",
        "VP Technology",
        "VP IT",
        "Director of Technology",
    ],
    pain_points=[
        "Integration complexity across ATS, VMS, payroll, and compliance systems",
        "Shadow IT — operations teams building rogue spreadsheet automations because Bullhorn reports aren't enough",
        "No unified data layer across the tech stack — each team has their own Excel kingdom",
        "AI governance concerns (bias, security, compliance) with every new vendor pitch",
        "Bullhorn One migration creates a 30-40% productivity drop during transition",
    ],
    language_style=(
        "Technical but strategic. Cares about architecture, security, data ownership, "
        "and integration patterns. Wants to understand that the Command Center reads "
        "from Bullhorn REST API, not a data warehouse. Values clean API boundaries "
        "and role-based access controls that map to Bullhorn user types."
    ),
    objections=[
        "How does this integrate with Bullhorn One?",
        "Where does our data live? Who owns it?",
        "What happens if we outgrow your platform?",
        "How do you handle AI governance and audit trails?",
        "What's the deployment model — is this an embedded Bullhorn app?",
    ],
    value_drivers=[
        "Embedded in Bullhorn — users never leave the system they already work in",
        "Reads directly from Bullhorn REST API — no separate data warehouse needed",
        "Role-based access controls mapped to Bullhorn user types (ATS User, PayBill Admin, Super Admin)",
        "Full audit trail on every action (exclusions, status changes, mass actions)",
        "Configurable filters map any Bullhorn custom field to the dashboard",
        "AI agents layer on top of the same dashboard — no new tools when upgrading",
    ],
    industry_context=(
        "Technology leaders in staffing firms running Bullhorn One. "
        "Evaluating operational intelligence platforms that embed directly in "
        "the ATS rather than adding another tool. AWS-hosted, SOC 2 infrastructure. "
        "The Command Center is their bridge from manual operations to AI-assisted."
    ),
)

ALL_PERSONAS: dict[str, Persona] = {
    p.key: p for p in [VP_OPS, CFO, CTO]
}


def get_persona(key: str) -> Persona:
    if key not in ALL_PERSONAS:
        valid = ", ".join(ALL_PERSONAS.keys())
        raise ValueError(f"Unknown persona '{key}'. Valid: {valid}")
    return ALL_PERSONAS[key]
