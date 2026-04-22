"""
Tier 2 — Client Memory for StaffingAgent.

Persistent per-tenant memory that stores learned patterns, known exceptions,
tolerance overrides, and alias maps. Every reconciliation/agent run can read
from and write back to client memory, making each subsequent run smarter.

Storage: simple JSON files under config/client_memory/{tenant_id}.json.
Graduate to a database or vector store when scale requires it.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "client_memory"


class ToleranceOverrides(BaseModel):
    """Per-client numeric tolerance overrides for reconciliation."""

    hours_mismatch_tolerance: float = Field(default=0.0, description="Acceptable hours diff before flagging")
    rate_mismatch_tolerance: float = Field(default=0.01, description="Acceptable rate diff ($)")
    financial_variance_threshold: float = Field(default=500.0, description="$ amount that forces HITL")
    confidence_threshold: float = Field(default=0.85, description="Score below which HITL triggers")


class KnownException(BaseModel):
    """A documented exception that agents should not flag as a discrepancy."""

    pattern: str = Field(description="What to match, e.g. 'PO format change Q2 2026'")
    description: str = Field(default="")
    added_date: str = Field(default="")
    expires: Optional[str] = Field(default=None, description="ISO date after which this exception no longer applies")


class ClientMemory(BaseModel):
    """Persistent memory for a single tenant / client."""

    tenant_id: str
    display_name: str = ""

    tolerance_overrides: ToleranceOverrides = Field(default_factory=ToleranceOverrides)

    client_aliases: dict[str, str] = Field(
        default_factory=dict,
        description="Map of known name variants to canonical name, e.g. {'GHR - General Healthcare': 'General Healthcare Resources'}",
    )

    known_exceptions: list[KnownException] = Field(
        default_factory=list,
        description="Documented exceptions agents should skip",
    )

    vms_quirks: list[str] = Field(
        default_factory=list,
        description="Known VMS platform behaviors, e.g. 'Beeline delays approval notifications by 24-48h'",
    )

    billing_rules: list[str] = Field(
        default_factory=list,
        description="Client-specific billing rules, e.g. 'Always rounds bill rate to nearest $0.50'",
    )

    escalation_contacts: dict[str, str] = Field(
        default_factory=dict,
        description="Role → contact for escalations, e.g. {'ap_manager': 'jane@client.com'}",
    )

    learned_patterns: list[str] = Field(
        default_factory=list,
        description="Patterns discovered by agents over time, appended after each run",
    )

    notes: str = ""


def load_client_memory(tenant_id: str) -> ClientMemory:
    """Load client memory from disk. Returns defaults if file doesn't exist."""
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _MEMORY_DIR / f"{tenant_id}.json"
    if not path.exists():
        logger.info("No client memory found for '%s' — using defaults", tenant_id)
        return ClientMemory(tenant_id=tenant_id)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return ClientMemory.model_validate(data)


def save_client_memory(memory: ClientMemory) -> Path:
    """Persist client memory to disk. Returns the file path."""
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _MEMORY_DIR / f"{memory.tenant_id}.json"
    with path.open("w", encoding="utf-8") as f:
        f.write(memory.model_dump_json(indent=2))
    logger.info("Client memory saved for '%s' → %s", memory.tenant_id, path)
    return path


def append_learned_pattern(tenant_id: str, pattern: str) -> None:
    """Convenience: load memory, append a pattern, save."""
    mem = load_client_memory(tenant_id)
    if pattern not in mem.learned_patterns:
        mem.learned_patterns.append(pattern)
        save_client_memory(mem)
        logger.info("Learned pattern for '%s': %s", tenant_id, pattern)
