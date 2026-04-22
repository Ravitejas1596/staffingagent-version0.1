"""
Sync the CEO Daily Brief to Notion.

Creates two records per day:
  1. A page in the Daily Briefs database (full brief archive)
  2. Task items in the CEO Task Board database (Kanban)

Requires environment variables:
  NOTION_API_KEY              — from Notion integration settings
  NOTION_DAILY_BRIEFS_DB_ID  — 32-char ID from the Daily Briefs database URL
  NOTION_TASKS_DB_ID         — 32-char ID from the CEO Task Board database URL

See docs/notion-setup-guide.md for step-by-step setup instructions.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict:
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NOTION_API_KEY environment variable not set. "
            "See docs/notion-setup-guide.md for setup instructions."
        )
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _rich_text(content: str) -> list:
    """Wrap a plain string in Notion's rich_text format."""
    return [{"type": "text", "text": {"content": content[:2000]}}]


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(text)},
    }


def _heading_block(text: str, level: int = 2) -> dict:
    heading_type = f"heading_{level}"
    return {
        "object": "block",
        "type": heading_type,
        heading_type: {"rich_text": _rich_text(text)},
    }


def _bullet_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(text)},
    }


def _divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def create_daily_brief_page(brief: dict) -> str:
    """
    Create a page in the Daily Briefs Notion database.

    Returns the URL of the created page.
    """
    db_id = os.environ.get("NOTION_DAILY_BRIEFS_DB_ID", "")
    if not db_id:
        print("  NOTION_DAILY_BRIEFS_DB_ID not set — skipping Daily Briefs page creation")
        return ""

    date_str = brief.get("date", datetime.utcnow().strftime("%A, %B %d, %Y"))
    priorities = brief.get("priorities", [])
    full_analysis = brief.get("full_analysis", "")
    pipeline = brief.get("pipeline", {})
    key_metric = brief.get("key_metric", {})

    top_priority = priorities[0] if priorities else "No priorities generated"

    # Build page content blocks
    blocks = [
        _heading_block("Today's Top 3 Priorities", 2),
    ]
    for i, p in enumerate(priorities[:3], 1):
        blocks.append(_bullet_block(f"{i}. {p}"))

    blocks.append(_divider_block())
    blocks.append(_heading_block("Pipeline Pulse", 2))
    company = pipeline.get("company", "No active deals")
    stage = pipeline.get("stage", "")
    action = pipeline.get("next_action", "")
    blocks.append(_paragraph_block(f"{company} — {stage}" if stage else company))
    if action:
        blocks.append(_paragraph_block(f"Next action: {action}"))

    blocks.append(_divider_block())
    blocks.append(_heading_block("Key Metric", 2))
    metric_val = key_metric.get("value", "")
    metric_label = key_metric.get("label", "")
    metric_ctx = key_metric.get("context", "")
    blocks.append(_paragraph_block(f"{metric_val} — {metric_label}"))
    if metric_ctx:
        blocks.append(_paragraph_block(metric_ctx))

    if full_analysis:
        blocks.append(_divider_block())
        blocks.append(_heading_block("Full AI Analysis", 2))
        # Split into chunks (Notion block limit is 2000 chars per block)
        chunk_size = 1800
        for i in range(0, len(full_analysis), chunk_size):
            blocks.append(_paragraph_block(full_analysis[i:i + chunk_size]))

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Name": {"title": _rich_text(f"CEO Brief — {date_str}")},
            "Date": {"date": {"start": datetime.utcnow().strftime("%Y-%m-%d")}},
            "Top Priority": {"rich_text": _rich_text(top_priority)},
            "Status": {"select": {"name": "Unread"}},
        },
        "children": blocks[:100],  # Notion allows max 100 blocks per request
    }

    response = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=_headers(),
        json=payload,
        timeout=30,
    )

    if response.status_code == 200:
        page_url = response.json().get("url", "")
        print(f"  Daily brief page created in Notion: {page_url}")
        return page_url
    else:
        print(f"  Warning: Failed to create Notion brief page: {response.status_code} {response.text[:200]}")
        return ""


def sync_tasks_to_board(brief: dict) -> str:
    """
    Add new tasks from the daily brief to the CEO Task Board database.

    Avoids duplicating tasks that were already added on a previous day
    (checks by task name). Returns the Notion Tasks database URL.
    """
    db_id = os.environ.get("NOTION_TASKS_DB_ID", "")
    if not db_id:
        print("  NOTION_TASKS_DB_ID not set — skipping task board sync")
        return ""

    tasks = brief.get("open_tasks", [])
    if not tasks:
        print("  No tasks to sync to Notion")
        return f"https://www.notion.so/{db_id.replace('-', '')}"

    # Fetch existing task names to avoid duplicates
    existing_names: set[str] = set()
    try:
        query_response = requests.post(
            f"{NOTION_API_BASE}/databases/{db_id}/query",
            headers=_headers(),
            json={"page_size": 100},
            timeout=30,
        )
        if query_response.status_code == 200:
            for page in query_response.json().get("results", []):
                title_prop = page.get("properties", {}).get("Task", {})
                title_items = title_prop.get("title", [])
                if title_items:
                    existing_names.add(title_items[0].get("text", {}).get("content", "").lower())
    except Exception as e:
        print(f"  Warning: Could not fetch existing tasks (will add all): {e}")

    added = 0
    skipped = 0

    for task in tasks:
        task_name = task.get("name", "")
        if not task_name:
            continue

        if task_name.lower() in existing_names:
            skipped += 1
            continue

        category = task.get("category", "General")
        priority = task.get("priority", "Med")
        source = task.get("source", "Daily Brief")

        # Map priority to Notion select option
        priority_map = {"High": "High", "Med": "Medium", "Low": "Low"}
        notion_priority = priority_map.get(priority, "Medium")

        payload = {
            "parent": {"database_id": db_id},
            "properties": {
                "Task": {"title": _rich_text(task_name)},
                "Category": {"select": {"name": category}},
                "Priority": {"select": {"name": notion_priority}},
                "Status": {"select": {"name": "To Do"}},
                "Source": {"rich_text": _rich_text(source)},
                "Date Added": {"date": {"start": datetime.now(timezone.utc).strftime("%Y-%m-%d")}},
            },
        }

        response = requests.post(
            f"{NOTION_API_BASE}/pages",
            headers=_headers(),
            json=payload,
            timeout=30,
        )

        if response.status_code == 200:
            added += 1
            existing_names.add(task_name.lower())
        else:
            print(f"  Warning: Failed to add task '{task_name}': {response.status_code}")

    print(f"  Notion task board: {added} tasks added, {skipped} already existed")
    return f"https://www.notion.so/{db_id.replace('-', '')}"


def sync_to_notion(brief: dict) -> tuple[str, str]:
    """
    Sync the full daily brief to Notion.

    Returns (brief_page_url, tasks_db_url).
    """
    print("Syncing to Notion...")
    brief_url = create_daily_brief_page(brief)
    tasks_url = sync_tasks_to_board(brief)
    return brief_url, tasks_url
