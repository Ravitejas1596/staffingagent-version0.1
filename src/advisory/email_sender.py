"""
Send the CEO Daily Brief via Resend API as a clean HTML email.

Requires environment variable:
  RESEND_API_KEY    — from resend.com (free tier: 3,000 emails/month)
  CHRIS_EMAIL       — recipient address (e.g. chris.scowden@staffingagent.ai)

Resend free tier allows sending from onboarding@resend.dev as the from address
without domain verification. Once staffingagent.ai domain is verified in Resend,
update FROM_ADDRESS below to use your own domain.
"""
from __future__ import annotations

import os
from datetime import datetime

import requests

RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS = "StaffingAgent CEO OS <onboarding@resend.dev>"
FROM_ADDRESS_VERIFIED = "StaffingAgent CEO OS <ceo-os@staffingagent.ai>"


def _get_from_address() -> str:
    """Use verified domain address if configured, otherwise fall back to Resend default."""
    use_verified = os.environ.get("RESEND_USE_VERIFIED_DOMAIN", "false").lower() == "true"
    return FROM_ADDRESS_VERIFIED if use_verified else FROM_ADDRESS


def render_html_email(brief: dict) -> str:
    """Render the daily brief dict as a clean HTML email."""
    date_str = brief.get("date", datetime.utcnow().strftime("%A, %B %d, %Y"))
    priorities = brief.get("priorities", [])
    pipeline = brief.get("pipeline", {})
    legal = brief.get("legal", {})
    key_metric = brief.get("key_metric", {})
    open_tasks = brief.get("open_tasks", [])
    notion_brief_url = brief.get("notion_brief_url", "")
    notion_tasks_url = brief.get("notion_tasks_url", "")

    # Priority rows
    priority_rows = ""
    for i, p in enumerate(priorities[:3], 1):
        priority_rows += f"""
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;vertical-align:top;">
            <span style="display:inline-block;width:24px;height:24px;background:#0d9488;color:#fff;
                         border-radius:50%;text-align:center;line-height:24px;font-size:12px;
                         font-weight:700;margin-right:12px;">{i}</span>
            <span style="font-size:15px;color:#1e293b;">{p}</span>
          </td>
        </tr>"""

    # Open tasks (first 5)
    task_rows = ""
    for task in open_tasks[:5]:
        category = task.get("category", "")
        name = task.get("name", "")
        priority = task.get("priority", "")
        color = {"High": "#ef4444", "Med": "#f59e0b", "Low": "#94a3b8"}.get(priority, "#94a3b8")
        task_rows += f"""
        <tr>
          <td style="padding:8px 16px;border-bottom:1px solid #f8fafc;font-size:13px;color:#475569;">
            <span style="display:inline-block;padding:2px 8px;background:{color}22;color:{color};
                         border-radius:4px;font-size:11px;font-weight:600;margin-right:8px;">{priority}</span>
            <span style="color:#64748b;font-size:11px;margin-right:8px;">[{category}]</span>
            {name}
          </td>
        </tr>"""

    pipeline_company = pipeline.get("company", "No active deals")
    pipeline_stage = pipeline.get("stage", "")
    pipeline_action = pipeline.get("next_action", "")
    pipeline_days = pipeline.get("days_since_contact", "")

    legal_complete = legal.get("complete", 0)
    legal_total = legal.get("total", 9)
    legal_next = legal.get("next_overdue", "All current")
    legal_pct = int((legal_complete / legal_total) * 100) if legal_total else 0

    metric_label = key_metric.get("label", "")
    metric_value = key_metric.get("value", "")
    metric_context = key_metric.get("context", "")

    notion_links = ""
    if notion_tasks_url:
        notion_links += f'<a href="{notion_tasks_url}" style="display:inline-block;margin:4px 8px 4px 0;padding:10px 20px;background:#0d9488;color:#fff;text-decoration:none;border-radius:6px;font-size:13px;font-weight:600;">Open Task Board →</a>'
    if notion_brief_url:
        notion_links += f'<a href="{notion_brief_url}" style="display:inline-block;margin:4px 8px 4px 0;padding:10px 20px;background:#f1f5f9;color:#334155;text-decoration:none;border-radius:6px;font-size:13px;font-weight:600;">View Full Brief →</a>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>CEO Daily Brief — {date_str}</title></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- Header -->
  <tr>
    <td style="background:#080d1a;border-radius:12px 12px 0 0;padding:28px 32px;">
      <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:.1em;color:#2dd4bf;text-transform:uppercase;">StaffingAgent.ai</p>
      <h1 style="margin:0 0 4px;font-size:22px;font-weight:800;color:#fff;">CEO Daily Brief</h1>
      <p style="margin:0;font-size:13px;color:#94a3b8;">{date_str}</p>
    </td>
  </tr>

  <!-- Top 3 Priorities -->
  <tr>
    <td style="background:#fff;padding:0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding:20px 32px 8px;">
            <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:.08em;color:#0d9488;text-transform:uppercase;">Today's Top 3 Priorities</p>
          </td>
        </tr>
        {priority_rows}
      </table>
    </td>
  </tr>

  <!-- Pipeline Pulse -->
  <tr>
    <td style="background:#fff;padding:0;border-top:1px solid #f1f5f9;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding:20px 32px 16px;">
            <p style="margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:.08em;color:#0d9488;text-transform:uppercase;">Pipeline Pulse</p>
            <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#1e293b;">
              {pipeline_company}
              {f'<span style="font-weight:400;color:#64748b;"> &mdash; {pipeline_stage}</span>' if pipeline_stage else ''}
            </p>
            {f'<p style="margin:4px 0 0;font-size:13px;color:#475569;">Next: {pipeline_action}</p>' if pipeline_action else ''}
            {f'<p style="margin:4px 0 0;font-size:12px;color:#94a3b8;">Last contact: {pipeline_days} days ago</p>' if pipeline_days else ''}
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Legal Checklist + Key Metric (2-col) -->
  <tr>
    <td style="background:#f8fafc;border-top:1px solid #f1f5f9;border-bottom:1px solid #f1f5f9;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="50%" style="padding:20px 16px 20px 32px;vertical-align:top;">
            <p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:.08em;color:#0d9488;text-transform:uppercase;">Legal Checklist</p>
            <div style="background:#e2e8f0;border-radius:4px;height:6px;margin-bottom:8px;">
              <div style="background:#0d9488;border-radius:4px;height:6px;width:{legal_pct}%;"></div>
            </div>
            <p style="margin:0 0 4px;font-size:20px;font-weight:800;color:#1e293b;">{legal_complete}<span style="font-size:14px;color:#94a3b8;font-weight:400;">/{legal_total}</span></p>
            <p style="margin:0;font-size:12px;color:#64748b;">Next: {legal_next}</p>
          </td>
          <td width="50%" style="padding:20px 32px 20px 16px;vertical-align:top;border-left:1px solid #e2e8f0;">
            <p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:.08em;color:#0d9488;text-transform:uppercase;">Key Metric</p>
            <p style="margin:0 0 4px;font-size:26px;font-weight:800;color:#0d9488;line-height:1;">{metric_value}</p>
            <p style="margin:0 0 4px;font-size:13px;font-weight:600;color:#334155;">{metric_label}</p>
            <p style="margin:0;font-size:12px;color:#94a3b8;">{metric_context}</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Open Tasks -->
  {f'''<tr>
    <td style="background:#fff;padding:0;border-top:1px solid #f1f5f9;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td style="padding:20px 32px 8px;">
          <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:.08em;color:#0d9488;text-transform:uppercase;">Open Tasks</p>
        </td></tr>
        {task_rows}
      </table>
    </td>
  </tr>''' if task_rows else ''}

  <!-- Notion Links -->
  {f'''<tr>
    <td style="background:#fff;padding:20px 32px 24px;border-top:1px solid #f1f5f9;">
      {notion_links}
    </td>
  </tr>''' if notion_links else ''}

  <!-- Footer -->
  <tr>
    <td style="background:#f1f5f9;border-radius:0 0 12px 12px;padding:16px 32px;">
      <p style="margin:0;font-size:11px;color:#94a3b8;">
        StaffingAgent.ai &mdash; CEO Operating System &mdash; Generated {date_str}<br>
        Update <code style="font-size:10px;background:#e2e8f0;padding:1px 4px;border-radius:3px;">docs/current-state.md</code> to change tomorrow's priorities.
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def send_daily_brief(brief: dict) -> bool:
    """
    Send the daily brief HTML email via Resend.

    Returns True on success, raises RuntimeError on failure.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("CHRIS_EMAIL", "chris.scowden@staffingagent.ai")

    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY environment variable not set. "
            "Sign up at resend.com and add the key as a GitHub secret."
        )

    date_str = brief.get("date", datetime.utcnow().strftime("%A, %B %d, %Y"))
    html_body = render_html_email(brief)

    response = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": _get_from_address(),
            "to": [recipient],
            "subject": f"CEO Daily Brief — {date_str}",
            "html": html_body,
        },
        timeout=30,
    )

    if response.status_code in (200, 201):
        email_id = response.json().get("id", "unknown")
        print(f"  Email sent successfully (id: {email_id}) to {recipient}")
        return True
    else:
        raise RuntimeError(
            f"Resend API returned {response.status_code}: {response.text}"
        )
