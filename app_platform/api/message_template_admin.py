"""Admin API for message-template overrides.

Scope:

- ``GET /api/v1/admin/message-templates`` — list platform defaults and the
  calling tenant's overrides in one response so the admin UI can show an
  "override this" affordance inline with each default.
- ``PUT /api/v1/admin/message-templates/{template_key}`` — upsert a
  tenant-scoped override for the specified key + language. Creates on first
  call, updates the existing active row on subsequent calls.
- ``DELETE /api/v1/admin/message-templates/{template_key}`` — mark the
  tenant's override inactive so the platform default resumes.

Auth: tenant admin role or higher. Super admins calling through the
platform session have full cross-tenant access.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select, update

from app_platform.api.auth import TokenPayload, require_super_admin
from app_platform.api.database import get_platform_session, get_tenant_session
from app_platform.api.message_templates import (
    ALLOWED_CHANNELS,
    ALLOWED_VARIABLES,
    TemplateVariableError,
)
from app_platform.api.models import MessageTemplate

router = APIRouter(prefix="/api/v1/admin/message-templates", tags=["admin-templates"])


class TemplateOut(BaseModel):
    id: str
    tenant_id: Optional[str]
    template_key: str
    channel: str
    language: str
    subject: Optional[str]
    body: str
    active: bool
    source: str  # 'tenant_override' | 'platform_default'
    updated_at: str


class TemplateUpsert(BaseModel):
    channel: str = Field(..., description="sms | email_subject | email_body")
    language: str = Field(default="en", min_length=2, max_length=8)
    subject: Optional[str] = None
    body: str = Field(..., min_length=1, max_length=5000)


def _to_out(row: MessageTemplate) -> TemplateOut:
    return TemplateOut(
        id=str(row.id),
        tenant_id=str(row.tenant_id) if row.tenant_id else None,
        template_key=row.template_key,
        channel=row.channel,
        language=row.language,
        subject=row.subject,
        body=row.body,
        active=row.active,
        source="tenant_override" if row.tenant_id else "platform_default",
        updated_at=row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else "",
    )


def _validate_body_variables(body: str, subject: str | None) -> None:
    """Parse the template for ``{{ var }}`` references and reject unknowns.

    This is a best-effort check at upload time so tenant admins get the
    error in the form instead of at agent runtime. The sandboxed render
    in ``message_templates.render`` is the authoritative gate.
    """
    import re

    pattern = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\|[^}]*)?\}\}")
    referenced: set[str] = set()
    for haystack in (body, subject or ""):
        referenced.update(pattern.findall(haystack))
    unknown = referenced - ALLOWED_VARIABLES
    if unknown:
        raise TemplateVariableError(
            f"Template references unknown variables: {sorted(unknown)}. "
            f"Allowed: {sorted(ALLOWED_VARIABLES)}"
        )


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    tenant_id: str = Query(..., description="Tenant to show alongside platform defaults"),
    language: str = Query(default="en"),
    _: TokenPayload = Depends(require_super_admin),
) -> list[TemplateOut]:
    """List platform defaults plus the tenant's active overrides for *language*."""
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id must be a UUID")

    async with get_platform_session() as session:
        stmt = (
            select(MessageTemplate)
            .where(
                and_(
                    MessageTemplate.active.is_(True),
                    MessageTemplate.language == language,
                )
            )
            .where(
                (MessageTemplate.tenant_id.is_(None))
                | (MessageTemplate.tenant_id == tenant_uuid)
            )
            .order_by(MessageTemplate.template_key.asc(), MessageTemplate.tenant_id.asc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [_to_out(r) for r in rows]


@router.put("/{template_key}", response_model=TemplateOut)
async def upsert_template(
    template_key: str,
    body: TemplateUpsert,
    tenant_id: str = Query(...),
    _: TokenPayload = Depends(require_super_admin),
) -> TemplateOut:
    """Create or update a tenant-scoped override for *template_key*."""
    if body.channel not in ALLOWED_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail=f"channel must be one of {sorted(ALLOWED_CHANNELS)}",
        )
    try:
        _validate_body_variables(body.body, body.subject)
    except TemplateVariableError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id must be a UUID")

    async with get_tenant_session(tenant_id) as session:
        existing_stmt = select(MessageTemplate).where(
            and_(
                MessageTemplate.tenant_id == tenant_uuid,
                MessageTemplate.template_key == template_key,
                MessageTemplate.language == body.language,
                MessageTemplate.active.is_(True),
            )
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()

        if existing is None:
            row = MessageTemplate(
                tenant_id=tenant_uuid,
                template_key=template_key,
                channel=body.channel,
                language=body.language,
                subject=body.subject,
                body=body.body,
                active=True,
            )
            session.add(row)
            await session.flush()
            return _to_out(row)

        existing.channel = body.channel
        existing.subject = body.subject
        existing.body = body.body
        await session.flush()
        return _to_out(existing)


@router.delete("/{template_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_override(
    template_key: str,
    tenant_id: str = Query(...),
    language: str = Query(default="en"),
    _: TokenPayload = Depends(require_super_admin),
) -> None:
    """Deactivate the tenant's override; platform default resumes next render."""
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="tenant_id must be a UUID")

    async with get_tenant_session(tenant_id) as session:
        stmt = (
            update(MessageTemplate)
            .where(
                and_(
                    MessageTemplate.tenant_id == tenant_uuid,
                    MessageTemplate.template_key == template_key,
                    MessageTemplate.language == language,
                    MessageTemplate.active.is_(True),
                )
            )
            .values(active=False)
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="No active override to delete.")
