"""Load persona instruction files from docs/claude-skills/."""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


SKILLS_DIR = Path(__file__).parent.parent.parent / "docs" / "claude-skills"

PERSONAS: dict[str, str] = {
    "CFO": "ai-cfo.md",
    "Chief of Staff": "ai-chief-of-staff.md",
    "GTM Lead": "ai-gtm-lead.md",
    "Product Lead": "ai-product-lead.md",
    "Risk Advisor": "ai-risk-advisor.md",
}


class Persona(NamedTuple):
    name: str
    instructions: str


def load_personas() -> list[Persona]:
    """Return all personas with their instruction text loaded from disk."""
    result = []
    for name, filename in PERSONAS.items():
        path = SKILLS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Persona file not found: {path}. "
                "Run from the workspace root or check docs/claude-skills/ directory."
            )
        instructions = path.read_text(encoding="utf-8")
        result.append(Persona(name=name, instructions=instructions))
    return result


def load_master_context() -> str:
    """Return the master business context document."""
    path = SKILLS_DIR / "00-master-context.md"
    if not path.exists():
        raise FileNotFoundError(f"Master context not found: {path}")
    return path.read_text(encoding="utf-8")
