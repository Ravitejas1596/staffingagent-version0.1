"""SQLAlchemy ORM models matching the database schema.

All tenant-scoped models include a tenant_id column.
RLS is enforced at the PostgreSQL level; these models
are the Python-side representation for queries and writes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(Text, default="assess")
    bullhorn_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    bullhorn_credentials_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    bullhorn_credentials_version: Mapped[int] = mapped_column(Integer, default=1)
    bullhorn_credentials_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    client_memory: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Twilio / A2P 10DLC per-tenant configuration (migration 048).
    # A2P brand is per-customer to preserve SMS deliverability attribution.
    twilio_messaging_service_sid: Mapped[str | None] = mapped_column(Text, nullable=True)
    twilio_a2p_brand_status: Mapped[str] = mapped_column(Text, default="not_registered")
    twilio_a2p_brand_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email"),
        Index("idx_users_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, default="viewer")
    bullhorn_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    permissions: Mapped[dict] = mapped_column(JSONB, default=dict)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Placement(Base):
    __tablename__ = "placements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "bullhorn_id"),
        Index("idx_placements_tenant", "tenant_id"),
        Index("idx_placements_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    bullhorn_id: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_name: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    client_name: Mapped[str | None] = mapped_column(Text)
    pay_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    bill_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    ot_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    start_date: Mapped[datetime | None] = mapped_column(Date)
    end_date: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    po_number: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    # Timesheet-cycle cache (migration 047). Authoritative source is Bullhorn's
    # placement.timesheet-cycle field; values sync on each placement refresh.
    timesheet_cycle_frequency: Mapped[str | None] = mapped_column(Text, nullable=True)
    timesheet_cycle_anchor_day: Mapped[str | None] = mapped_column(Text, nullable=True)
    timesheet_cycle_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Timesheet(Base):
    __tablename__ = "timesheets"
    __table_args__ = (
        Index("idx_timesheets_tenant", "tenant_id"),
        Index("idx_timesheets_week", "tenant_id", "week_ending"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    bullhorn_id: Mapped[str | None] = mapped_column(Text)
    placement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("placements.id"))
    candidate_name: Mapped[str | None] = mapped_column(Text)
    week_ending: Mapped[datetime] = mapped_column(Date, nullable=False)
    regular_hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    ot_hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    bill_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    ot_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VMSRecord(Base):
    __tablename__ = "vms_records"
    __table_args__ = (
        Index("idx_vms_tenant", "tenant_id"),
        Index("idx_vms_week", "tenant_id", "week_ending"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    upload_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    vms_platform: Mapped[str | None] = mapped_column(Text)
    placement_ref: Mapped[str | None] = mapped_column(Text)
    candidate_name: Mapped[str | None] = mapped_column(Text)
    week_ending: Mapped[datetime | None] = mapped_column(Date)
    regular_hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    ot_hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    bill_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    ot_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))
    per_diem: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    po_number: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    source_type: Mapped[str] = mapped_column(Text, default="file")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VMSUpload(Base):
    __tablename__ = "vms_uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    vms_platform: Mapped[str | None] = mapped_column(Text)
    record_count: Mapped[int | None] = mapped_column(Integer)
    column_mapping: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("idx_invoices_tenant", "tenant_id"),
        Index("idx_invoices_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    bullhorn_id: Mapped[str | None] = mapped_column(Text)
    invoice_number: Mapped[str | None] = mapped_column(Text)
    client_name: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str | None] = mapped_column(Text)
    invoice_date: Mapped[datetime | None] = mapped_column(Date)
    due_date: Mapped[datetime | None] = mapped_column(Date)
    paid_date: Mapped[datetime | None] = mapped_column(Date)
    days_outstanding: Mapped[int | None] = mapped_column(Integer)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentRun(Base):
    """Tracks agent execution lifecycle: planning -> plan_ready -> approved -> executing -> completed.

    Status values:
        planning, plan_ready, approved, executing, completed, completed_with_errors, cancelled, error
    """
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    agent_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending")
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    trigger_type: Mapped[str] = mapped_column(Text, default="manual")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONB)
    execution_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentPlanAction(Base):
    """Individual action within an agent's plan. Each action goes through
    approval_status (pending -> approved/rejected/skipped) and then
    execution_status (pending -> success/failed/manual_required)."""
    __tablename__ = "agent_plan_actions"
    __table_args__ = (
        Index("idx_plan_actions_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_ref: Mapped[str | None] = mapped_column(Text)
    target_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    severity: Mapped[str | None] = mapped_column(Text)
    financial_impact: Mapped[float | None] = mapped_column(Numeric(12, 2))
    details: Mapped[dict | None] = mapped_column(JSONB)
    approval_status: Mapped[str] = mapped_column(Text, default="pending")
    execution_status: Mapped[str] = mapped_column(Text, default="pending")
    execution_result: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentResult(Base):
    __tablename__ = "agent_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id"))
    record_ref: Mapped[str | None] = mapped_column(Text)
    candidate_name: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    discrepancies: Mapped[dict] = mapped_column(JSONB, default=list)
    compliance_flags: Mapped[dict] = mapped_column(JSONB, default=list)
    llm_explanation: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(Text)
    financial_impact: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    review_status: Mapped[str] = mapped_column(Text, default="pending")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vms_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    ats_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VMSMatch(Base):
    __tablename__ = "vms_matches"
    __table_args__ = (
        Index("idx_vms_matches_tenant", "tenant_id"),
        Index("idx_vms_matches_run", "run_id"),
        Index("idx_vms_matches_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=True)
    vms_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vms_records.id"))
    placement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("placements.id"), nullable=True)
    bullhorn_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    match_method: Mapped[str | None] = mapped_column(Text)
    name_similarity: Mapped[float | None] = mapped_column(Numeric(4, 3))
    rate_delta: Mapped[float | None] = mapped_column(Numeric(10, 2))
    hours_delta: Mapped[float | None] = mapped_column(Numeric(8, 2))
    financial_impact: Mapped[float | None] = mapped_column(Numeric(12, 2))
    llm_explanation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VMSNameAlias(Base):
    __tablename__ = "vms_name_aliases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "vms_name"),
        Index("idx_vms_aliases_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    vms_name: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_first: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_last: Mapped[str] = mapped_column(Text, nullable=False)
    bullhorn_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    learned_from: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vms_matches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RoleChangeAudit(Base):
    """Append-only record of every user role change.

    Written by the role-assignment helper in app_platform.api.users so we
    can detect any path that escalates privileges. See migration 043.
    """
    __tablename__ = "role_change_audit"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    caller_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    from_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_role: Mapped[str] = mapped_column(Text, nullable=False)
    via_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_resource: Mapped[str] = mapped_column(Text, default="")
    input_hash: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="success")
    human_approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    verification_status: Mapped[str | None] = mapped_column(Text)
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ─── Time Anomaly Agent v1 models ──────────────────────────────────────
# Reference: files/Time_Anomaly_Agent_v1_Build_Spec.md (Cortney) +
# .cursor/plans/time_anomaly_v1_build.plan.md.


class ExceptionRegistry(Base):
    """Shared exception / dismissal / suppression registry consulted by every
    agent's Detect stage before firing an alert. Migration 044."""

    __tablename__ = "exception_registry"
    __table_args__ = (
        Index(
            "idx_exception_registry_app_lookup",
            "tenant_id",
            "agent_id",
            "alert_type",
            "entity_type",
            "entity_id",
        ),
    )

    exception_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    magnitude_threshold: Mapped[float | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )
    original_magnitude: Mapped[float | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentAlert(Base):
    """Alert lifecycle container. One row per fired alert, tracks state
    machine progression. Migration 045."""

    __tablename__ = "agent_alerts"
    __table_args__ = (
        Index("idx_agent_alerts_app_tenant_state", "tenant_id", "agent_type", "state"),
        Index(
            "idx_agent_alerts_app_placement_period",
            "tenant_id",
            "placement_id",
            "pay_period_start",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(Text, nullable=False)
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="detected")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    placement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="SET NULL"),
        nullable=True,
    )
    # candidates table is created separately (migration 003) — no ORM model yet.
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    pay_period_start: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    pay_period_end: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    trigger_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    langgraph_thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    outreach_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_reminder_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class AgentAlertEvent(Base):
    """Append-only event stream for an agent alert. Migration 046.

    Application code MUST NOT update or delete rows in this table; an explicit
    database trigger blocks UPDATE and the cascade from agent_alerts is the
    only legitimate delete path. Use compensating events (event_type='reversed'
    with reverses_event_id set) to undo actions.
    """

    __tablename__ = "agent_alert_events"
    __table_args__ = (
        Index("idx_agent_alert_events_app_alert", "alert_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    reversal_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    prior_state_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reverses_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_alert_events.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class MessageTemplate(Base):
    """Per-tenant message template override. tenant_id=NULL is platform
    default. Migration 049."""

    __tablename__ = "message_templates"
    __table_args__ = (
        Index(
            "idx_message_templates_app_lookup",
            "template_key",
            "language",
            "tenant_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    template_key: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class AgentSetting(Base):
    """Per-tenant per-agent configuration override. Platform defaults live in
    agent code; this table only holds tenant-specific overrides.
    Migration 051."""

    __tablename__ = "agent_settings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "agent_type", "setting_key", name="uq_agent_settings_tenant_agent_key"
        ),
        Index("idx_agent_settings_app_lookup", "tenant_id", "agent_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(Text, nullable=False)
    setting_key: Mapped[str] = mapped_column(Text, nullable=False)
    setting_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
