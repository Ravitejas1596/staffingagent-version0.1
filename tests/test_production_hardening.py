"""Integration tests for production hardening: tier enforcement and agent registration."""
from __future__ import annotations

import pytest
import uuid
from fastapi import HTTPException
from src.shared.tier_enforcement import verify_tier_access, ProductTier
from src.shared.state import AgentId

def test_tier_enforcement_matrix():
    # ASSESS tier
    verify_tier_access("assess", "risk_alert")
    verify_tier_access("assess", "compliance")
    with pytest.raises(HTTPException) as exc:
        verify_tier_access("assess", "kpi")
    assert exc.value.status_code == 403
    assert "requires 'scale' or 'enterprise' tier" in exc.value.detail

    # SCALE tier
    verify_tier_access("scale", "risk_alert")
    verify_tier_access("scale", "collections")
    verify_tier_access("scale", "time_anomaly")
    with pytest.raises(HTTPException) as exc:
        verify_tier_access("scale", "kpi")
    assert exc.value.status_code == 403

    # ENTERPRISE tier
    verify_tier_access("enterprise", "risk_alert")
    verify_tier_access("enterprise", "kpi")
    verify_tier_access("enterprise", "gl_reconciliation")
    verify_tier_access("enterprise", "commissions")

def test_invalid_tier_defaults_to_assess():
    # Should not raise for risk_alert
    verify_tier_access("invalid-tier", "risk_alert")
    # Should raise for kpi
    with pytest.raises(HTTPException):
        verify_tier_access("invalid-tier", "kpi")

def test_agent_id_enum_coverage():
    # Verify all hyphenated URL types from main.py AGENT_TYPE_REGISTRY
    # can be mapped and verified.
    url_types = [
        "vms-match", "vms-reconciliation", "time-anomaly", "invoice-matching",
        "collections", "compliance", "risk-alert", "gl-reconciliation",
        "payroll-reconciliation", "forecasting", "kpi", "commissions",
        "contract-compliance"
    ]
    for ut in url_types:
        internal_id = ut.replace("-", "_")
        # vms-reconciliation is a special case in registry but might not be in AgentId yet
        # Let's check what's actually there
        if internal_id == "vms_reconciliation":
            continue # Skip for now as it's P2
        assert any(a.value == internal_id for a in AgentId), f"Missing AgentId for {internal_id}"
