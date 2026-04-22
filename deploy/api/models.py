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
    Date,
    ForeignKey,
    Index,
    Integer,
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
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    client_memory: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


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
    permissions: Mapped[dict] = mapped_column(JSONB, default=dict)
    bullhorn_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    synced_at: Mapped[datetime] = mapped_column(default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    synced_at: Mapped[datetime] = mapped_column(default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column()


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
    synced_at: Mapped[datetime] = mapped_column(default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    agent_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending")
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    trigger_type: Mapped[str] = mapped_column(Text, default="manual")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_summary: Mapped[dict | None] = mapped_column(JSONB)
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    reviewed_at: Mapped[datetime | None] = mapped_column()
    vms_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    ats_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
