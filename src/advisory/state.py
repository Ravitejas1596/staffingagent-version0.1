"""Load current business state from docs/current-state.md."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
STATE_FILE = DOCS_DIR / "current-state.md"
TEMPLATE_FILE = DOCS_DIR / "weekly-state-template.md"


def load_current_state() -> str:
    """
    Return the current weekly state update.

    Raises FileNotFoundError if current-state.md doesn't exist or still
    contains only the template placeholder text (not yet filled in).
    """
    if not STATE_FILE.exists():
        raise FileNotFoundError(
            f"Current state file not found: {STATE_FILE}\n"
            "Copy docs/weekly-state-template.md to docs/current-state.md, "
            "fill it in, and commit before running the advisory report."
        )

    content = STATE_FILE.read_text(encoding="utf-8")

    # Guard: detect unfilled template (still has the [WEEK_START_DATE] placeholder)
    if "[WEEK_START_DATE]" in content:
        raise ValueError(
            "docs/current-state.md still contains template placeholders. "
            "Please fill in the current week's state before running the advisory report."
        )

    return content


def get_report_date() -> str:
    """Return today's date as a formatted string for use in report titles."""
    return datetime.utcnow().strftime("%B %d, %Y")


def get_report_week() -> str:
    """Return the ISO week number and year for report labeling."""
    now = datetime.utcnow()
    return f"Week {now.isocalendar()[1]}, {now.year}"
