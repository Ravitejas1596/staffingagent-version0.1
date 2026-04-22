"""CRUD API for per-tenant agent settings (thresholds + routing).

Scope:

- ``GET /api/v1/agents/{agent_type}/settings`` — list current settings
  for the authenticated tenant, showing platform defaults merged with
  any tenant overrides.
- ``PUT /api/v1/agents/{agent_type}/settings/{key}`` — upsert a
  tenant-scoped override for a single setting key.
- ``DELETE /api/v1/agents/{agent_type}/settings/{key}`` — remove the
  tenant's override so the platform default resumes.
- ``GET /api/v1/agents/{agent_type}/settings/schema`` — return the
  available settings with types, ranges, and descriptions so the UI
  can render input fields dynamically.

Auth: tenant admin role or higher.
"""
from __future__ import annotations

import uuid
from dataclasses import fields as dc_fields
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, select

from app_platform.api.auth import TokenPayload, get_current_user
from app_platform.api.database import get_tenant_session
from app_platform.api.models import AgentSetting

router = APIRouter(prefix="/api/v1/agents", tags=["agent-settings"])


# ── Pydantic schemas ─────────────────────────────────────────────────

class SettingOut(BaseModel):
    key: str
    value: Any
    source: str  # 'platform_default' | 'tenant_override'
    description: str = ""


class SettingUpsert(BaseModel):
    value: Any = Field(..., description="The value to set")


class SettingSchemaField(BaseModel):
    key: str
    type: str  # 'float', 'int', 'str'
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    description: str = ""
    unit: str = ""  # '%', 'hours', 'days', '$'


# ── Agent config registry ────────────────────────────────────────────
#
# Maps agent_type → (config_class, field_metadata).
# The metadata is what the /schema endpoint returns so the UI can
# render inputs dynamically.

_AGENT_SCHEMAS: dict[str, list[SettingSchemaField]] = {
    "time_anomaly": [
        SettingSchemaField(key="group_b.reg_hours_limit", type="float", default=40.0, min=10, max=80, description="Regular hours limit before alert", unit="hours"),
        SettingSchemaField(key="group_b.ot_hours_limit", type="float", default=20.0, min=5, max=60, description="Overtime hours limit before alert", unit="hours"),
        SettingSchemaField(key="group_b.total_hours_limit", type="float", default=60.0, min=20, max=168, description="Total hours limit before alert", unit="hours"),
        SettingSchemaField(key="group_a.consecutive_miss_threshold", type="int", default=2, min=1, max=10, description="Consecutive pay periods missed before escalation"),
        SettingSchemaField(key="group_c.tolerance_pct", type="float", default=0.25, min=0.05, max=1.0, description="Variance tolerance from typical pattern", unit="%"),
        SettingSchemaField(key="group_c.lookback_weeks", type="int", default=8, min=2, max=26, description="Weeks of history for variance baseline"),
        SettingSchemaField(key="group_c.suppression_window_days", type="int", default=60, min=7, max=180, description="Days to suppress duplicate variance alerts", unit="days"),
        SettingSchemaField(key="group_c.magnitude_multiplier", type="float", default=2.0, min=1.0, max=10.0, description="Re-fire multiplier for variance magnitude"),
    ],
    "vms_matching": [
        SettingSchemaField(key="auto_accept_threshold", type="float", default=0.95, min=0.5, max=1.0, description="Auto-accept matches above this confidence", unit="%"),
        SettingSchemaField(key="needs_review_threshold", type="float", default=0.70, min=0.3, max=1.0, description="Require human review below this confidence", unit="%"),
        SettingSchemaField(key="fuzzy_match_min_score", type="float", default=0.85, min=0.5, max=1.0, description="Minimum fuzzy match score to consider", unit="%"),
        SettingSchemaField(key="rate_variance_tolerance_pct", type="float", default=5.0, min=0, max=50, description="Acceptable bill rate variance", unit="%"),
        SettingSchemaField(key="date_range_tolerance_days", type="int", default=30, min=0, max=180, description="Date range tolerance for matching", unit="days"),
    ],
    "risk_alert": [
        SettingSchemaField(key="minimum_wage", type="float", default=7.25, min=0, max=50, description="Minimum wage threshold", unit="$"),
        SettingSchemaField(key="high_pay_rate", type="float", default=150.0, min=50, max=500, description="High pay rate flag threshold", unit="$"),
        SettingSchemaField(key="high_bill_rate", type="float", default=225.0, min=50, max=1000, description="High bill rate flag threshold", unit="$"),
        SettingSchemaField(key="low_markup_pct", type="float", default=10.0, min=0, max=100, description="Low markup warning threshold", unit="%"),
        SettingSchemaField(key="high_markup_pct", type="float", default=250.0, min=50, max=500, description="High markup warning threshold", unit="%"),
        SettingSchemaField(key="high_hours", type="float", default=60.0, min=20, max=168, description="High weekly hours flag", unit="hours"),
        SettingSchemaField(key="high_pay_amount", type="float", default=5000.0, min=100, max=100000, description="High pay amount flag threshold", unit="$"),
        SettingSchemaField(key="high_bill_amount", type="float", default=7500.0, min=100, max=100000, description="High bill amount flag threshold", unit="$"),
    ],
    "collections": [
        SettingSchemaField(key="reminder_days", type="int", default=15, min=1, max=90, description="Days past due before first reminder", unit="days"),
        SettingSchemaField(key="followup_days", type="int", default=30, min=7, max=120, description="Days past due before follow-up", unit="days"),
        SettingSchemaField(key="escalation_days", type="int", default=60, min=14, max=180, description="Days past due before escalation", unit="days"),
        SettingSchemaField(key="legal_escalation_days", type="int", default=90, min=30, max=365, description="Days past due before legal escalation", unit="days"),
        SettingSchemaField(key="high_priority_amount", type="float", default=10000.0, min=1000, max=500000, description="Amount threshold for high priority", unit="$"),
        SettingSchemaField(key="critical_priority_amount", type="float", default=50000.0, min=5000, max=1000000, description="Amount threshold for critical priority", unit="$"),
    ],
    "compliance": [
        SettingSchemaField(key="credential_expiry_warning_days", type="int", default=30, min=7, max=180, description="Days before expiry to warn", unit="days"),
        SettingSchemaField(key="credential_expiry_critical_days", type="int", default=7, min=1, max=30, description="Days before expiry for critical alert", unit="days"),
        SettingSchemaField(key="max_consecutive_weeks_without_review", type="int", default=12, min=4, max=52, description="Weeks without review before flag"),
        SettingSchemaField(key="overtime_weekly_threshold_hours", type="float", default=40.0, min=20, max=80, description="Weekly OT threshold", unit="hours"),
    ],
    "invoice_matching": [
        SettingSchemaField(key="amount_tolerance_pct", type="float", default=2.0, min=0, max=20, description="Invoice-to-PO amount tolerance", unit="%"),
        SettingSchemaField(key="auto_approve_confidence", type="float", default=0.95, min=0.5, max=1.0, description="Auto-approve above this confidence", unit="%"),
        SettingSchemaField(key="review_confidence", type="float", default=0.70, min=0.3, max=1.0, description="Require review below this confidence", unit="%"),
        SettingSchemaField(key="max_days_between_invoice_and_po", type="int", default=90, min=30, max=365, description="Max days between invoice and PO", unit="days"),
    ],
    "vms_reconciliation": [
        SettingSchemaField(key="auto_approve_confidence", type="float", default=0.90, min=0.5, max=1.0, description="Auto-approve above this confidence", unit="%"),
        SettingSchemaField(key="review_confidence", type="float", default=0.60, min=0.3, max=1.0, description="Require review below this confidence", unit="%"),
        SettingSchemaField(key="hours_tolerance_pct", type="float", default=5.0, min=0, max=25, description="Hours tolerance between VMS and ATS", unit="%"),
        SettingSchemaField(key="rate_tolerance_pct", type="float", default=5.0, min=0, max=25, description="Rate tolerance between VMS and ATS", unit="%"),
        SettingSchemaField(key="max_records_per_batch", type="int", default=50, min=10, max=200, description="Max records per reconciliation batch"),
    ],
    "gl_reconciliation": [
        SettingSchemaField(key="amount_tolerance_pct", type="float", default=1.0, min=0, max=20, description="GL to charge amount tolerance", unit="%"),
        SettingSchemaField(key="auto_approve_confidence", type="float", default=0.95, min=0.5, max=1.0, description="Auto-approve above this confidence", unit="%"),
        SettingSchemaField(key="max_unmatched_entries", type="int", default=50, min=1, max=500, description="Max unmatched entries before halt"),
    ],
    "payroll_reconciliation": [
        SettingSchemaField(key="amount_tolerance_pct", type="float", default=0.5, min=0, max=10, description="Payroll to payable amount tolerance", unit="%"),
        SettingSchemaField(key="auto_approve_confidence", type="float", default=0.98, min=0.5, max=1.0, description="Auto-approve above this confidence", unit="%"),
        SettingSchemaField(key="tax_withholding_tolerance", type="float", default=0.05, min=0, max=1.0, description="Tax withholding variance tolerance", unit="$"),
    ],
    "forecasting": [
        SettingSchemaField(key="lookback_months", type="int", default=12, min=1, max=36, description="Months of history to analyze", unit="months"),
        SettingSchemaField(key="forecast_horizon_weeks", type="int", default=12, min=1, max=52, description="Weeks to forecast forward", unit="weeks"),
        SettingSchemaField(key="growth_assumption_pct", type="float", default=0.0, min=-50, max=100, description="Assumed weekly growth rate", unit="%"),
    ],
    "kpi": [
        SettingSchemaField(key="target_fill_rate_pct", type="float", default=85.0, min=0, max=100, description="Target fill rate for jobs", unit="%"),
        SettingSchemaField(key="target_margin_pct", type="float", default=25.0, min=0, max=100, description="Target gross margin percentage", unit="%"),
        SettingSchemaField(key="max_dso_days", type="int", default=45, min=1, max=180, description="Target maximum Days Sales Outstanding", unit="days"),
    ],
    "commissions": [
        SettingSchemaField(key="default_recruiter_rate_pct", type="float", default=5.0, min=0, max=100, description="Default recruiter commission on spread", unit="%"),
        SettingSchemaField(key="default_sales_rate_pct", type="float", default=3.0, min=0, max=100, description="Default sales rep commission on spread", unit="%"),
    ],
    "contract_compliance": [
        SettingSchemaField(key="notify_days_before_end", type="int", default=30, min=1, max=180, description="Days before contract end to notify", unit="days"),
        SettingSchemaField(key="max_bill_rate_variance_pct", type="float", default=5.0, min=0, max=50, description="Allowed bill rate variance from MSA", unit="%"),
        SettingSchemaField(key="tenure_limit_months", type="int", default=24, min=1, max=120, description="Maximum worker tenure on one contract", unit="months"),
    ],
}

VALID_AGENT_TYPES = set(_AGENT_SCHEMAS.keys())


def _require_admin(user: TokenPayload) -> None:
    """Raise 403 unless the user has admin or super_admin role."""
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin role required for agent settings")


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/{agent_type}/settings/schema", response_model=list[SettingSchemaField])
async def get_settings_schema(
    agent_type: str,
    user: TokenPayload = Depends(get_current_user),
) -> list[SettingSchemaField]:
    """Return the available settings for an agent type with validation metadata.

    The UI uses this to dynamically render input fields with labels,
    types, ranges, and units.
    """
    if agent_type not in VALID_AGENT_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown agent_type: {agent_type}")
    return _AGENT_SCHEMAS[agent_type]


@router.get("/{agent_type}/settings", response_model=list[SettingOut])
async def list_settings(
    agent_type: str,
    user: TokenPayload = Depends(get_current_user),
) -> list[SettingOut]:
    """List settings for the authenticated tenant, merged with defaults.

    Each setting shows whether it's using the platform default or a
    tenant override.
    """
    if agent_type not in VALID_AGENT_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown agent_type: {agent_type}")

    schema = _AGENT_SCHEMAS[agent_type]
    tenant_id = uuid.UUID(user.tenant_id)

    async with get_tenant_session(user.tenant_id) as session:
        stmt = select(AgentSetting).where(
            and_(
                AgentSetting.tenant_id == tenant_id,
                AgentSetting.agent_type == agent_type,
            )
        )
        rows = (await session.execute(stmt)).scalars().all()
        overrides = {row.setting_key: row.setting_value for row in rows}

    result = []
    for field in schema:
        if field.key in overrides:
            result.append(SettingOut(
                key=field.key,
                value=overrides[field.key],
                source="tenant_override",
                description=field.description,
            ))
        else:
            result.append(SettingOut(
                key=field.key,
                value=field.default,
                source="platform_default",
                description=field.description,
            ))
    return result


@router.put("/{agent_type}/settings/{key}", response_model=SettingOut)
async def upsert_setting(
    agent_type: str,
    key: str,
    body: SettingUpsert,
    user: TokenPayload = Depends(get_current_user),
) -> SettingOut:
    """Create or update a tenant-scoped override for a single setting."""
    _require_admin(user)

    if agent_type not in VALID_AGENT_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown agent_type: {agent_type}")

    schema = _AGENT_SCHEMAS[agent_type]
    field = next((f for f in schema if f.key == key), None)
    if field is None:
        valid_keys = [f.key for f in schema]
        raise HTTPException(
            status_code=422,
            detail=f"Unknown setting key '{key}' for {agent_type}. Valid keys: {valid_keys}",
        )

    # Validate value against schema constraints.
    try:
        if field.type == "float":
            v = float(body.value)
        elif field.type == "int":
            v = int(body.value)
        else:
            v = str(body.value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"Setting '{key}' requires type {field.type}, got {type(body.value).__name__}",
        )

    if field.min is not None and v < field.min:
        raise HTTPException(
            status_code=422,
            detail=f"Setting '{key}' minimum is {field.min}, got {v}",
        )
    if field.max is not None and v > field.max:
        raise HTTPException(
            status_code=422,
            detail=f"Setting '{key}' maximum is {field.max}, got {v}",
        )

    tenant_id = uuid.UUID(user.tenant_id)
    async with get_tenant_session(user.tenant_id) as session:
        existing = (
            await session.execute(
                select(AgentSetting).where(
                    and_(
                        AgentSetting.tenant_id == tenant_id,
                        AgentSetting.agent_type == agent_type,
                        AgentSetting.setting_key == key,
                    )
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.setting_value = v
            existing.updated_by = uuid.UUID(user.user_id) if user.user_id else None
            await session.flush()
        else:
            row = AgentSetting(
                tenant_id=tenant_id,
                agent_type=agent_type,
                setting_key=key,
                setting_value=v,
                updated_by=uuid.UUID(user.user_id) if user.user_id else None,
            )
            session.add(row)
            await session.flush()

    return SettingOut(
        key=key,
        value=v,
        source="tenant_override",
        description=field.description,
    )


@router.delete("/{agent_type}/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    agent_type: str,
    key: str,
    user: TokenPayload = Depends(get_current_user),
) -> None:
    """Remove a tenant override so the platform default resumes."""
    _require_admin(user)

    if agent_type not in VALID_AGENT_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown agent_type: {agent_type}")

    tenant_id = uuid.UUID(user.tenant_id)
    async with get_tenant_session(user.tenant_id) as session:
        result = await session.execute(
            delete(AgentSetting).where(
                and_(
                    AgentSetting.tenant_id == tenant_id,
                    AgentSetting.agent_type == agent_type,
                    AgentSetting.setting_key == key,
                )
            )
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="No override found to delete")
