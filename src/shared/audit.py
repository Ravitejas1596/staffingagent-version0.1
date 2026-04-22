"""
Audit logging service for StaffingAgent agents.

Every agent action writes an AuditLogEntry. Entries are appended to a
per-tenant JSONL file under config/audit_logs/ and can be forwarded to
a database or SIEM in production.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from src.shared.state import (
    ActionType,
    AgentId,
    AuditLogEntry,
    AuditStatus,
)

logger = logging.getLogger(__name__)

_AUDIT_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "audit_logs"


def compute_input_hash(data: Any) -> str:
    """SHA-256 of JSON-serialized input for tamper detection."""
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def write_audit_entry(entry: AuditLogEntry, *, tenant_id: str = "default") -> None:
    """Append an audit entry to the tenant's JSONL log file."""
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    path = _AUDIT_DIR / f"{tenant_id}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")
    logger.debug("audit | %s | %s | %s | %s", entry.agent_id, entry.action_type, entry.status, entry.target_resource)


@contextmanager
def audit_context(
    agent_id: AgentId,
    action_type: ActionType,
    *,
    tenant_id: str = "default",
    target_resource: str = "",
    parent_task_id: Optional[str] = None,
    input_data: Any = None,
    human_approval_required: bool = False,
) -> Generator[AuditLogEntry, None, None]:
    """Context manager that times an operation and writes the audit entry on exit.

    Usage::

        with audit_context(AgentId.VMS, ActionType.MATCH, tenant_id="ghr") as entry:
            # ... do work ...
            entry.output_summary = "Matched 18 of 20 records"
    """
    entry = AuditLogEntry(
        agent_id=agent_id,
        action_type=action_type,
        client_id=tenant_id,
        target_resource=target_resource,
        parent_task_id=parent_task_id,
        human_approval_required=human_approval_required,
        input_hash=compute_input_hash(input_data) if input_data is not None else "",
    )
    t0 = time.perf_counter()
    try:
        yield entry
    except Exception as exc:
        entry.status = AuditStatus.FAILURE
        entry.output_summary = str(exc)[:500]
        raise
    finally:
        entry.duration_ms = int((time.perf_counter() - t0) * 1000)
        write_audit_entry(entry, tenant_id=tenant_id)
