"""Tier-based product gating for StaffingAgent agents.

Defines which agents are available at each subscription level.
Tiers:
- assess: Foundation risk and compliance monitoring.
- scale: Full operational automation (AR, time, matching).
- enterprise: Strategic advanced agents (GL, Forecasting, KPI, Commissions).
"""
from __future__ import annotations
from enum import Enum
from typing import Set
from fastapi import HTTPException, status
from src.shared.state import AgentId

class ProductTier(str, Enum):
    ASSESS = "assess"
    SCALE = "scale"
    ENTERPRISE = "enterprise"

# Mapping of tier -> set of allowed agent IDs
TIER_PERMISSIONS: dict[ProductTier, Set[AgentId]] = {
    ProductTier.ASSESS: {
        AgentId.RISK_ALERT,
        AgentId.COMPLIANCE,
    },
    ProductTier.SCALE: {
        AgentId.RISK_ALERT,
        AgentId.COMPLIANCE,
        AgentId.COLLECTIONS,
        AgentId.TIME_ANOMALY,
        AgentId.INVOICE_MATCHING,
        AgentId.VMS_MATCH,
    },
    ProductTier.ENTERPRISE: {
        AgentId.RISK_ALERT,
        AgentId.COMPLIANCE,
        AgentId.COLLECTIONS,
        AgentId.TIME_ANOMALY,
        AgentId.INVOICE_MATCHING,
        AgentId.VMS_MATCH,
        AgentId.GL_RECONCILIATION,
        AgentId.PAYROLL_RECONCILIATION,
        AgentId.FORECASTING,
        AgentId.KPI,
        AgentId.COMMISSIONS,
        AgentId.CONTRACT_COMPLIANCE,
    }
}

def verify_tier_access(tenant_tier: str, agent_id: str) -> None:
    """Check if the given agent_id is allowed for the tenant's tier.
    
    Raises 403 if access is denied.
    """
    try:
        tier = ProductTier(tenant_tier.lower())
    except ValueError:
        tier = ProductTier.ASSESS  # Default to lowest
        
    allowed = TIER_PERMISSIONS.get(tier, TIER_PERMISSIONS[ProductTier.ASSESS])
    
    if agent_id not in [a.value for a in allowed]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent '{agent_id}' requires '{ProductTier.SCALE.value}' or '{ProductTier.ENTERPRISE.value}' tier. Your current tier is '{tier.value}'."
        )
