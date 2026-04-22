"""StaffingAgent.ai — Platform API

Multi-tenant FastAPI backend for the Command Center.
All tenant-scoped endpoints require JWT auth; the database session
is automatically scoped to the authenticated tenant via PostgreSQL RLS.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select, text

from platform.api.auth import (
    TokenPayload,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from platform.api.config import settings
from platform.api.database import engine, get_tenant_session
from platform.api.chat import router as chat_router
from platform.api.users import router as users_router
from platform.api.models import (
    AgentResult,
    AgentRun,
    AuditLog,
    Invoice,
    Placement,
    Tenant,
    Timesheet,
    User,
    VMSMatch,
    VMSNameAlias,
    VMSRecord,
    VMSUpload,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="StaffingAgent.ai API",
    version="0.1.0",
    description="Multi-tenant Command Center API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(users_router)


# ── Health ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── Auth ─────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_slug: str


class LoginUserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    permissions: dict[str, dict[str, bool]]
    is_active: bool
    invited_by: str | None = None
    invited_by_name: str | None = None
    invited_at: str | None = None
    last_login_at: str | None = None
    created_at: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    user_id: str
    role: str
    name: str
    user: LoginUserOut


def _user_to_login_out(user: User) -> LoginUserOut:
    from platform.api.users import effective_permissions
    return LoginUserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        permissions=effective_permissions(user.role, user.permissions),
        is_active=user.is_active,
        invited_by=str(user.invited_by) if user.invited_by else None,
        invited_by_name=None,
        invited_at=user.invited_at.isoformat() if user.invited_at else None,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Authenticate with email + password. Returns JWT scoped to tenant."""
    from datetime import datetime, timezone
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        tenant_row = await session.execute(
            select(Tenant).where(Tenant.slug == body.tenant_slug, Tenant.is_active.is_(True))
        )
        tenant = tenant_row.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=401, detail="Invalid tenant")

        await session.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant.id)})
        user_row = await session.execute(
            select(User).where(User.email == body.email, User.is_active.is_(True))
        )
        user = user_row.scalar_one_or_none()
        if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user.last_login_at = datetime.now(timezone.utc)
        await session.commit()

        token = create_access_token(str(user.id), str(tenant.id), user.role)
        return LoginResponse(
            access_token=token,
            tenant_id=str(tenant.id),
            user_id=str(user.id),
            role=user.role,
            name=user.name,
            user=_user_to_login_out(user),
        )


@app.get("/api/v1/auth/me", response_model=LoginUserOut)
async def get_me(current_user: TokenPayload = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    async with get_tenant_session(current_user.tenant_id) as session:
        row = await session.execute(select(User).where(User.id == current_user.sub))
        user = row.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return _user_to_login_out(user)


# ── Dashboard Metrics ────────────────────────────────────────

@app.get("/api/v1/dashboard/metrics")
async def dashboard_metrics(current_user: TokenPayload = Depends(get_current_user)):
    """Aggregated metrics for all entity panels on the main dashboard."""
    async with get_tenant_session(current_user.tenant_id) as session:
        placement_count = await session.scalar(select(func.count(Placement.id)))
        timesheet_count = await session.scalar(select(func.count(Timesheet.id)))
        invoice_count = await session.scalar(select(func.count(Invoice.id)))
        vms_count = await session.scalar(select(func.count(VMSRecord.id)))

        pending_review = await session.scalar(
            select(func.count(AgentResult.id)).where(
                AgentResult.requires_review.is_(True),
                AgentResult.review_status == "pending",
            )
        )

        return {
            "placements": {"total": placement_count or 0},
            "timesheets": {"total": timesheet_count or 0},
            "invoices": {"total": invoice_count or 0},
            "vms_records": {"total": vms_count or 0},
            "review_queue": {"pending": pending_review or 0},
        }


# ── Placements ───────────────────────────────────────────────

@app.get("/api/v1/placements")
async def list_placements(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: TokenPayload = Depends(get_current_user),
):
    async with get_tenant_session(current_user.tenant_id) as session:
        q = select(Placement).order_by(Placement.created_at.desc()).limit(limit).offset(offset)
        if status:
            q = q.where(Placement.status == status)
        rows = await session.execute(q)
        return [_row_to_dict(r) for r in rows.scalars().all()]


# ── Timesheets ───────────────────────────────────────────────

@app.get("/api/v1/timesheets")
async def list_timesheets(
    week_ending: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: TokenPayload = Depends(get_current_user),
):
    async with get_tenant_session(current_user.tenant_id) as session:
        q = select(Timesheet).order_by(Timesheet.week_ending.desc()).limit(limit).offset(offset)
        if week_ending:
            q = q.where(Timesheet.week_ending == week_ending)
        if status:
            q = q.where(Timesheet.status == status)
        rows = await session.execute(q)
        return [_row_to_dict(r) for r in rows.scalars().all()]


# ── VMS Uploads ──────────────────────────────────────────────

@app.get("/api/v1/vms/uploads")
async def list_vms_uploads(current_user: TokenPayload = Depends(get_current_user)):
    async with get_tenant_session(current_user.tenant_id) as session:
        rows = await session.execute(
            select(VMSUpload).order_by(VMSUpload.created_at.desc()).limit(50)
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]


@app.post("/api/v1/vms/uploads/presign")
async def create_upload_presign(
    filename: str,
    vms_platform: str = "unknown",
    current_user: TokenPayload = Depends(get_current_user),
):
    """Generate an S3 pre-signed URL for the client to upload a VMS file directly."""
    import uuid

    import boto3

    upload_id = str(uuid.uuid4())
    s3_key = f"{current_user.tenant_id}/{upload_id}/{filename}"

    s3_kwargs: dict[str, Any] = {"region_name": settings.aws_default_region}
    if settings.aws_endpoint_url:
        s3_kwargs["endpoint_url"] = settings.aws_endpoint_url

    s3 = boto3.client("s3", **s3_kwargs)

    try:
        s3.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        s3.create_bucket(Bucket=settings.s3_bucket)

    presigned_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": s3_key},
        ExpiresIn=3600,
    )

    async with get_tenant_session(current_user.tenant_id) as session:
        upload = VMSUpload(
            id=uuid.UUID(upload_id),
            tenant_id=uuid.UUID(current_user.tenant_id),
            uploaded_by=uuid.UUID(current_user.sub),
            filename=filename,
            s3_key=s3_key,
            vms_platform=vms_platform,
        )
        session.add(upload)

    return {
        "upload_id": upload_id,
        "presigned_url": presigned_url,
        "s3_key": s3_key,
    }


# ── Agents ───────────────────────────────────────────────────

@app.get("/api/v1/agents/runs")
async def list_agent_runs(
    agent_type: str | None = None,
    limit: int = 20,
    current_user: TokenPayload = Depends(get_current_user),
):
    async with get_tenant_session(current_user.tenant_id) as session:
        q = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
        if agent_type:
            q = q.where(AgentRun.agent_type == agent_type)
        rows = await session.execute(q)
        return [_row_to_dict(r) for r in rows.scalars().all()]


@app.get("/api/v1/agents/runs/{run_id}/results")
async def get_run_results(
    run_id: str,
    severity: str | None = None,
    requires_review: bool | None = None,
    current_user: TokenPayload = Depends(get_current_user),
):
    async with get_tenant_session(current_user.tenant_id) as session:
        q = select(AgentResult).where(AgentResult.run_id == run_id)
        if severity:
            q = q.where(AgentResult.severity == severity)
        if requires_review is not None:
            q = q.where(AgentResult.requires_review == requires_review)
        q = q.order_by(AgentResult.confidence.asc())
        rows = await session.execute(q)
        return [_row_to_dict(r) for r in rows.scalars().all()]


class ReviewDecision(BaseModel):
    status: str  # approved, escalated, corrected, dismissed


@app.post("/api/v1/agents/results/{result_id}/review")
async def review_result(
    result_id: str,
    body: ReviewDecision,
    current_user: TokenPayload = Depends(get_current_user),
):
    """HITL: reviewer marks an agent result as approved/escalated/corrected/dismissed."""
    import uuid
    from datetime import datetime, timezone

    async with get_tenant_session(current_user.tenant_id) as session:
        row = await session.execute(select(AgentResult).where(AgentResult.id == result_id))
        result = row.scalar_one_or_none()
        if not result:
            raise HTTPException(status_code=404, detail="Result not found")
        result.review_status = body.status
        result.reviewed_by = uuid.UUID(current_user.sub)
        result.reviewed_at = datetime.now(timezone.utc)

    return {"id": result_id, "review_status": body.status}


# ── VMS Matching Agent ───────────────────────────────────────

class VMSMatchRejectRequest(BaseModel):
    corrected_placement_id: str | None = None  # UUID of the correct placement
    corrected_bullhorn_id: int | None = None
    notes: str | None = None


@app.post("/api/v1/agents/vms-match/invoke")
async def invoke_vms_match(
    weeks_back: int = 8,
    upload_id: str | None = None,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Trigger VMS matching run. Loads VMS records + placements, runs 3-node pipeline."""
    import uuid
    from datetime import datetime, timedelta, timezone

    from src.agents.vms_matching.graph import get_graph

    async with get_tenant_session(current_user.tenant_id) as session:
        # 1. Load VMS records
        vms_q = select(VMSRecord).where(VMSRecord.tenant_id == uuid.UUID(current_user.tenant_id))
        if upload_id:
            vms_q = vms_q.where(VMSRecord.upload_id == uuid.UUID(upload_id))
        else:
            cutoff = datetime.now(timezone.utc).date() - timedelta(weeks=weeks_back)
            vms_q = vms_q.where(VMSRecord.week_ending >= cutoff)
        vms_rows = (await session.execute(vms_q)).scalars().all()

        if not vms_rows:
            raise HTTPException(status_code=404, detail="No VMS records found for given criteria")

        # 2. Load placements
        placement_rows = (await session.execute(select(Placement))).scalars().all()

        # 3. Load known aliases for fast lookup
        alias_rows = (await session.execute(
            select(VMSNameAlias).where(VMSNameAlias.tenant_id == uuid.UUID(current_user.tenant_id))
        )).scalars().all()
        aliases = {" ".join(a.vms_name.lower().split()): _row_to_dict(a) for a in alias_rows}

        # 4. Create AgentRun record
        run = AgentRun(
            tenant_id=uuid.UUID(current_user.tenant_id),
            agent_type="vms-match",
            status="running",
            triggered_by=uuid.UUID(current_user.sub),
            trigger_type="manual",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.flush()

        # 5. Serialize for graph
        vms_records = [_row_to_dict(r) for r in vms_rows]
        placements = [
            {
                "placement_id": str(p.id),
                "bullhorn_id": p.bullhorn_id,
                "candidate_first": p.candidate_name.split()[0] if p.candidate_name else None,
                "candidate_last": " ".join(p.candidate_name.split()[1:]) if p.candidate_name and len(p.candidate_name.split()) > 1 else p.candidate_name,
                "client_name": p.client_name,
                "job_title": p.job_title,
                "bill_rate": float(p.bill_rate) if p.bill_rate else None,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "end_date": p.end_date.isoformat() if p.end_date else None,
            }
            for p in placement_rows
        ]

        # 6. Run graph
        try:
            graph = get_graph()
            result = graph.invoke({
                "tenant_id": current_user.tenant_id,
                "vms_records": vms_records,
                "placements": placements,
                "aliases": aliases,
            })
        except Exception as e:
            run.status = "error"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            return {"run_id": str(run.id), "status": "error", "error": str(e)}

        # 7. Persist each match
        matches = result.get("matches") or []
        for m in matches:
            rate_delta = m.get("rate_delta")
            reg_hours = float(m.get("regular_hours") or 0)
            ot_hours = float(m.get("ot_hours") or 0)
            financial_impact = round(abs(float(rate_delta or 0)) * (reg_hours + ot_hours), 2)

            vms_match = VMSMatch(
                tenant_id=uuid.UUID(current_user.tenant_id),
                run_id=run.id,
                vms_record_id=uuid.UUID(str(m["id"])),
                placement_id=uuid.UUID(m["matched_placement_id"]) if m.get("matched_placement_id") else None,
                bullhorn_id=m.get("matched_bullhorn_id"),
                confidence=m.get("confidence"),
                match_method=m.get("match_method"),
                name_similarity=m.get("name_similarity"),
                rate_delta=rate_delta,
                hours_delta=m.get("hours_delta"),
                financial_impact=financial_impact,
                llm_explanation=m.get("explanation"),
                status="approved" if float(m.get("confidence") or 0) >= 0.95 else "pending",
            )
            session.add(vms_match)

        # 8. Update run summary
        summary = result.get("result") or {}
        run.status = "success"
        run.result_summary = summary
        run.completed_at = datetime.now(timezone.utc)
        run.token_usage = result.get("token_usage")

    return {
        "run_id": str(run.id),
        "status": "success",
        **summary,
    }


@app.get("/api/v1/agents/vms-match/runs/{run_id}/matches")
async def get_vms_matches(
    run_id: str,
    status: str | None = None,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Get all VMS matches for a run, optionally filtered by status."""
    async with get_tenant_session(current_user.tenant_id) as session:
        q = select(VMSMatch).where(VMSMatch.run_id == uuid.UUID(run_id))
        if status:
            q = q.where(VMSMatch.status == status)
        q = q.order_by(VMSMatch.confidence.asc().nullslast())
        rows = (await session.execute(q)).scalars().all()
        return [_row_to_dict(r) for r in rows]


@app.post("/api/v1/agents/vms-match/matches/{match_id}/approve")
async def approve_vms_match(
    match_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Approve a proposed VMS match."""
    import uuid
    from datetime import datetime, timezone

    async with get_tenant_session(current_user.tenant_id) as session:
        row = await session.get(VMSMatch, uuid.UUID(match_id))
        if not row:
            raise HTTPException(status_code=404, detail="Match not found")
        row.status = "approved"
        row.reviewed_by = uuid.UUID(current_user.sub)
        row.reviewed_at = datetime.now(timezone.utc)
    return {"id": match_id, "status": "approved"}


@app.post("/api/v1/agents/vms-match/matches/{match_id}/reject")
async def reject_vms_match(
    match_id: str,
    body: VMSMatchRejectRequest,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Reject a proposed match. Optionally provide the correct placement to learn from."""
    import uuid
    from datetime import datetime, timezone

    async with get_tenant_session(current_user.tenant_id) as session:
        row = await session.get(VMSMatch, uuid.UUID(match_id))
        if not row:
            raise HTTPException(status_code=404, detail="Match not found")

        row.status = "corrected" if body.corrected_placement_id else "rejected"
        row.reviewed_by = uuid.UUID(current_user.sub)
        row.reviewed_at = datetime.now(timezone.utc)
        row.review_notes = body.notes

        # If a correction was provided, update the match and write a name alias
        if body.corrected_placement_id:
            row.placement_id = uuid.UUID(body.corrected_placement_id)
            if body.corrected_bullhorn_id:
                row.bullhorn_id = body.corrected_bullhorn_id

            # Load the VMS record to get its candidate_name
            vms_rec = await session.get(VMSRecord, row.vms_record_id)
            # Load the correct placement to get canonical name
            correct_placement = await session.get(Placement, uuid.UUID(body.corrected_placement_id))

            if vms_rec and correct_placement and correct_placement.candidate_name:
                parts = correct_placement.candidate_name.split()
                canonical_first = parts[0] if parts else ""
                canonical_last = " ".join(parts[1:]) if len(parts) > 1 else ""

                # Upsert alias
                existing = await session.execute(
                    select(VMSNameAlias).where(
                        VMSNameAlias.tenant_id == uuid.UUID(current_user.tenant_id),
                        VMSNameAlias.vms_name == vms_rec.candidate_name,
                    )
                )
                alias = existing.scalar_one_or_none()
                if alias:
                    alias.canonical_first = canonical_first
                    alias.canonical_last = canonical_last
                    alias.bullhorn_id = body.corrected_bullhorn_id
                    alias.learned_from = row.id
                else:
                    session.add(VMSNameAlias(
                        tenant_id=uuid.UUID(current_user.tenant_id),
                        vms_name=vms_rec.candidate_name,
                        canonical_first=canonical_first,
                        canonical_last=canonical_last,
                        bullhorn_id=body.corrected_bullhorn_id,
                        learned_from=row.id,
                    ))

    return {"id": match_id, "status": row.status}


@app.post("/api/v1/agents/vms-match/matches/{match_id}/dismiss")
async def dismiss_vms_match(
    match_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Dismiss a VMS record — no ATS match needed."""
    import uuid
    from datetime import datetime, timezone

    async with get_tenant_session(current_user.tenant_id) as session:
        row = await session.get(VMSMatch, uuid.UUID(match_id))
        if not row:
            raise HTTPException(status_code=404, detail="Match not found")
        row.status = "dismissed"
        row.reviewed_by = uuid.UUID(current_user.sub)
        row.reviewed_at = datetime.now(timezone.utc)
    return {"id": match_id, "status": "dismissed"}


# ── Audit Log ────────────────────────────────────────────────

@app.get("/api/v1/audit")
async def list_audit_log(
    limit: int = 50,
    current_user: TokenPayload = Depends(get_current_user),
):
    async with get_tenant_session(current_user.tenant_id) as session:
        rows = await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]


# ── Helpers ──────────────────────────────────────────────────

def _row_to_dict(obj: Any) -> dict[str, Any]:
    """Convert an ORM model instance to a JSON-safe dict."""
    d: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        elif hasattr(val, "hex"):
            val = str(val)
        d[col.name] = val
    return d
