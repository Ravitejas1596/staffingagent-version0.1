"""
Shared state types for StaffingAgent LangGraph agents.
All agents use a common base state; each agent extends with its own fields.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums for audit log
# ---------------------------------------------------------------------------

class AgentId(str, Enum):
    BRAIN = "brain"
    BILLING = "billing"
    VMS_MATCH = "vms_match"
    COMPLIANCE = "compliance"
    COLLECTIONS = "collections"
    VERIFICATION = "verification"
    TIME_ANOMALY = "time_anomaly"
    INVOICE_MATCHING = "invoice_matching"
    RISK_ALERT = "risk_alert"
    GL_RECONCILIATION = "gl_reconciliation"
    PAYROLL_RECONCILIATION = "payroll_reconciliation"
    FORECASTING = "forecasting"
    KPI = "kpi"
    COMMISSIONS = "commissions"
    CONTRACT_COMPLIANCE = "contract_compliance"


class ActionType(str, Enum):
    READ = "read"
    WRITE = "write"
    CALCULATE = "calculate"
    MATCH = "match"
    FLAG = "flag"
    ESCALATE = "escalate"
    DELEGATE = "delegate"
    VERIFY = "verify"
    COMPACT = "compact"


class AuditStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Audit log entry — every agent action writes one of these
# ---------------------------------------------------------------------------

class AuditLogEntry(BaseModel):
    """Structured audit record for every agent action.

    Includes input_hash for tamper detection and token_usage for billing.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: AgentId
    action_type: ActionType
    target_resource: str = Field(default="", description="E.g. 'Placement/PL-1002' or 'Invoice/INV-4401'")
    client_id: str = Field(default="", description="Tenant / client this action pertains to")
    input_hash: str = Field(default="", description="SHA-256 of input data for tamper detection")
    output_summary: str = Field(default="", max_length=500)
    status: AuditStatus = AuditStatus.SUCCESS
    human_approval_required: bool = False
    approved_by: Optional[str] = None
    parent_task_id: Optional[str] = Field(default=None, description="Links to orchestrator task for tracing")
    verification_status: Optional[VerificationStatus] = None
    token_usage: Optional[dict[str, Any]] = None
    duration_ms: int = 0


def as_dict(state: Any) -> dict[str, Any]:
    """Normalize state to a plain dict regardless of whether LangGraph passes a Pydantic model or dict."""
    if isinstance(state, dict):
        return state
    if hasattr(state, "model_dump"):
        return state.model_dump()
    return dict(state)


class AgentState(BaseModel):
    """Base state for all staffing agents. Extend per agent."""

    tenant_id: str = Field(default="default", description="Customer/tenant identifier")
    messages: list[dict[str, Any]] = Field(default_factory=list, description="Conversation / tool messages")
    result: Optional[dict[str, Any]] = Field(default=None, description="Final agent result for reporting")
    human_review_required: bool = Field(default=False, description="True when HITL approval needed")
    human_decision: Optional[dict[str, Any]] = Field(default=None, description="Human approval/rejection payload")
    error: Optional[str] = Field(default=None, description="Last error message if any")
    token_usage: list[dict[str, Any]] = Field(default_factory=list, description="Per-call token usage for billing")

    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}


class VMSReconciliationState(AgentState):
    """State for VMS reconciliation agent (e.g. B4Health ↔ Bullhorn)."""

    vms_records: list[dict[str, Any]] = Field(default_factory=list)
    ats_records: list[dict[str, Any]] = Field(default_factory=list)
    proposed_matches: list[dict[str, Any]] = Field(default_factory=list)
    unmatched_vms: list[dict[str, Any]] = Field(default_factory=list)
    unmatched_ats: list[dict[str, Any]] = Field(default_factory=list)


class InvoiceMatchingState(AgentState):
    """State for invoice/PO matching agent."""

    purchase_orders: list[dict[str, Any]] = Field(default_factory=list)
    invoices: list[dict[str, Any]] = Field(default_factory=list)
    proposed_matches: list[dict[str, Any]] = Field(default_factory=list)
    exceptions: list[dict[str, Any]] = Field(default_factory=list)


class TimeAnomalyState(AgentState):
    """State for time-entry anomaly detection agent."""

    time_entries: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    suggested_corrections: list[dict[str, Any]] = Field(default_factory=list)


class CollectionsState(AgentState):
    """State for collections / AR intelligence agent."""

    ar_aging: list[dict[str, Any]] = Field(default_factory=list)
    prioritization: list[dict[str, Any]] = Field(default_factory=list)
    suggested_actions: list[dict[str, Any]] = Field(default_factory=list)
    draft_messages: list[dict[str, Any]] = Field(default_factory=list)


class ComplianceState(AgentState):
    """State for compliance / governance agent."""

    policies: list[dict[str, Any]] = Field(default_factory=list)
    activity_log: list[dict[str, Any]] = Field(default_factory=list)
    violations: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)


class VMSMatchingState(AgentState):
    """State for the VMS name-matching agent (fuzzy + LLM matching pipeline)."""

    # Inputs
    vms_records: list[dict[str, Any]] = Field(default_factory=list)
    placements: list[dict[str, Any]] = Field(default_factory=list)
    aliases: dict[str, dict[str, Any]] = Field(default_factory=dict, description="vms_name → alias row from DB")

    # Pipeline outputs
    resolved: list[dict[str, Any]] = Field(default_factory=list, description="Records matched by alias/exact/fuzzy")
    unresolved: list[dict[str, Any]] = Field(default_factory=list, description="Records still needing LLM")
    llm_matches: list[dict[str, Any]] = Field(default_factory=list, description="Matches returned by Claude")

    # Final combined matches (all methods)
    matches: list[dict[str, Any]] = Field(default_factory=list)


class RiskAlertState(AgentState):
    """State for the risk alert agent."""
    placements: list[dict[str, Any]] = Field(default_factory=list)
    charges: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)


class GLReconciliationState(AgentState):
    """State for the GL reconciliation agent."""
    gl_entries: list[dict[str, Any]] = Field(default_factory=list)
    charges: list[dict[str, Any]] = Field(default_factory=list)
    matches: list[dict[str, Any]] = Field(default_factory=list)
    discrepancies: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)


class PayrollReconciliationState(AgentState):
    """State for the payroll reconciliation agent."""
    payroll_records: list[dict[str, Any]] = Field(default_factory=list)
    charges: list[dict[str, Any]] = Field(default_factory=list)
    matches: list[dict[str, Any]] = Field(default_factory=list)
    discrepancies: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)


class ForecastingState(AgentState):
    """State for the forecasting agent."""
    billing_history: list[dict[str, Any]] = Field(default_factory=list)
    payroll_history: list[dict[str, Any]] = Field(default_factory=list)
    trend_analysis: dict[str, Any] = Field(default_factory=dict)
    forecast: dict[str, Any] = Field(default_factory=dict)


class KPIState(AgentState):
    """State for the KPI agent."""
    metrics_data: dict[str, Any] = Field(default_factory=dict)
    computed_kpis: dict[str, Any] = Field(default_factory=dict)
    alerts: list[dict[str, Any]] = Field(default_factory=list)


class CommissionsState(AgentState):
    """State for the commissions agent."""
    placements: list[dict[str, Any]] = Field(default_factory=list)
    commissions: list[dict[str, Any]] = Field(default_factory=list)
    validation_results: dict[str, Any] = Field(default_factory=dict)


class ContractComplianceState(AgentState):
    """State for the contract compliance agent."""
    placements: list[dict[str, Any]] = Field(default_factory=list)
    contracts: list[dict[str, Any]] = Field(default_factory=list)
    violations: list[dict[str, Any]] = Field(default_factory=list)
