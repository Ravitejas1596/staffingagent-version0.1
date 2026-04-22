"""
Agent permission enforcement for StaffingAgent.

Loads the permission matrix from config/permissions.json and provides a
check_permission() gate that agents call before performing an action.
This ensures no agent exceeds its defined scope.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "permissions.json"


class PermissionDenied(Exception):
    """Raised when an agent attempts an action outside its permission scope."""


@lru_cache(maxsize=1)
def _load_matrix() -> dict[str, Any]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_agent_permissions(agent_id: str) -> dict[str, Any]:
    """Return the permission block for *agent_id*, or empty dict if unknown."""
    matrix = _load_matrix()
    return matrix.get("agents", {}).get(agent_id, {})


def check_permission(
    agent_id: str,
    action: str,
    resource: str,
) -> None:
    """Verify that *agent_id* is allowed to perform *action* on *resource*.

    Raises PermissionDenied if the action is not in the agent's scope.
    Actions: "read", "write", "send", "modify_financial", "override_compliance".
    """
    perms = get_agent_permissions(agent_id)
    if not perms:
        raise PermissionDenied(f"Unknown agent '{agent_id}' — no permissions defined")

    if action in ("modify_financial", "override_compliance"):
        if not perms.get(action, False):
            raise PermissionDenied(f"Agent '{agent_id}' denied: {action}")
        return

    allowed_resources: list[str] = perms.get(action, [])
    if not isinstance(allowed_resources, list):
        raise PermissionDenied(f"Agent '{agent_id}' denied: {action} on '{resource}'")

    if "ALL" in allowed_resources or resource in allowed_resources:
        return

    raise PermissionDenied(
        f"Agent '{agent_id}' denied: {action} on '{resource}' "
        f"(allowed: {allowed_resources})"
    )


def requires_human_approval(description: str) -> bool:
    """Check whether a proposed action matches an approval-gate rule.

    This is a coarse keyword check; production would use structured action
    metadata. Returns True if the action should be queued for human review.
    """
    matrix = _load_matrix()
    matrix.get("approval_gates", [])
    desc_lower = description.lower()
    gate_keywords = {
        "invoice amount": "modify",
        "client contact": "communication",
        "regulatory notification": "compliance",
        "financial records": "financial",
        "older than 90 days": "stale",
    }
    for keyword, _ in gate_keywords.items():
        if keyword in desc_lower:
            return True
    return False
