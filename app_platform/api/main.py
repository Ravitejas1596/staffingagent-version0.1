"""StaffingAgent.ai — Platform API  # noqa

Multi-tenant FastAPI backend for the Command Center.
All tenant-scoped endpoints require JWT auth; the database session
is automatically scoped to the authenticated tenant via PostgreSQL RLS.
"""
from __future__ import annotations

import datetime as _dt
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import case, func, select, text

from app_platform.api.auth import (
    TokenPayload,
    create_access_token,
    get_current_user,
    hash_password,
    require_super_admin,
    verify_password,
)
from app_platform.api.config import settings
from app_platform.api.database import engine, get_tenant_session
from app_platform.api.admin import router as admin_router
from app_platform.api.agent_settings import router as agent_settings_router
from app_platform.api.chat import router as chat_router
from app_platform.api.alerts import router as alerts_router
from app_platform.api.message_template_admin import router as message_template_admin_router
from app_platform.api.users import router as users_router
from app_platform.api.models import (
    AgentPlanAction,
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
from src.shared.tier_enforcement import verify_tier_access


async def _run_migrations_on_startup() -> None:
    """Run database migrations using the admin database URL.

    Uses DATABASE_ADMIN_URL (superuser) so migrations can CREATE tables.
    Falls back to the regular engine if DATABASE_ADMIN_URL is not set.
    """
    import os
    import re
    from pathlib import Path

    from sqlalchemy.ext.asyncio import create_async_engine

    admin_url = os.environ.get("DATABASE_ADMIN_URL", "")
    if admin_url:
        # Convert postgres:// → postgresql+asyncpg://
        admin_url = re.sub(r"^postgres(ql)?://", "postgresql+asyncpg://", admin_url)
        migrate_engine = create_async_engine(admin_url, echo=False)
    else:
        migrate_engine = engine

    migrations_dir = Path(__file__).resolve().parent.parent.parent / "deploy" / "db" / "migrations"
    if not migrations_dir.exists():
        print(f"[migrate] No migrations dir at {migrations_dir} — skipping", flush=True)
        return

    pattern = re.compile(r"^(\d{3})_.+\.sql$")
    all_migrations = []
    for f in sorted(migrations_dir.iterdir()):
        m = pattern.match(f.name)
        if m:
            all_migrations.append((m.group(1), f.name, f))

    if not all_migrations:
        print("[migrate] No migration files found — skipping", flush=True)
        return

    print(f"[migrate] Found {len(all_migrations)} migration file(s)", flush=True)

    from sqlalchemy.sql import text as sa_text
    async with migrate_engine.begin() as conn:
        await conn.execute(sa_text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  version TEXT PRIMARY KEY,"
            "  filename TEXT NOT NULL,"
            "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
            ")"
        ))

        rows = await conn.execute(sa_text("SELECT version FROM schema_migrations"))
        applied = {r[0] for r in rows.fetchall()}
        print(f"[migrate] Already applied: {len(applied)}", flush=True)

        has_tenants = (await conn.execute(sa_text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'tenants')"
        ))).scalar()
        needs_baseline = not applied and has_tenants

        if needs_baseline:
            print("[migrate] Auto-baseline: existing DB without migration history", flush=True)

        pending = [(v, fn, p) for v, fn, p in all_migrations if v not in applied]
        if not pending:
            print("[migrate] Database is up to date", flush=True)
            return

        print(f"[migrate] Processing {len(pending)} pending migration(s):", flush=True)

    strip_begin = re.compile(r"(?i)^\s*BEGIN\s*;\s*$", re.MULTILINE)
    strip_commit = re.compile(r"(?i)^\s*COMMIT\s*;\s*$", re.MULTILINE)

    applied_count = 0
    baselined_count = 0
    for version, filename, path in pending:
        raw_sql = path.read_text(encoding="utf-8")
        sql = strip_begin.sub("", raw_sql)
        sql = strip_commit.sub("", sql).strip()

        try:
            async with migrate_engine.begin() as conn:
                for statement in _split_sql_statements(sql):
                    if statement.strip():
                        await conn.execute(sa_text(statement))
                await conn.execute(
                    sa_text("INSERT INTO schema_migrations (version, filename) VALUES (:v, :f)"),
                    {"v": version, "f": filename},
                )
            print(f"[migrate]   [{version}] {filename} — applied", flush=True)
            applied_count += 1
        except Exception as e:
            if needs_baseline:
                try:
                    async with migrate_engine.begin() as conn:
                        await conn.execute(
                            sa_text("INSERT INTO schema_migrations (version, filename) VALUES (:v, :f)"),
                            {"v": version, "f": filename},
                        )
                except Exception:
                    pass
                print(f"[migrate]   [{version}] {filename} — baselined ({type(e).__name__})", flush=True)
                baselined_count += 1
            else:
                print(f"[migrate]   [{version}] {filename} — FAILED: {e}", flush=True)
                return

    parts = []
    if applied_count:
        parts.append(f"{applied_count} applied")
    if baselined_count:
        parts.append(f"{baselined_count} baselined")
    total = len(applied) + applied_count + baselined_count
    print(f"[migrate] Done — {total} total ({', '.join(parts)})", flush=True)

    if admin_url:
        await migrate_engine.dispose()


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL into individual statements, respecting function bodies and strings."""
    statements = []
    current: list[str] = []
    in_dollar_quote = False
    dollar_tag = ""

    for line in sql.split("\n"):
        stripped = line.strip()

        if in_dollar_quote:
            current.append(line)
            if dollar_tag in stripped:
                in_dollar_quote = False
            else:
                continue

        if stripped.startswith("--"):
            continue

        import re as _re
        dq = _re.findall(r"\$[^$]*\$", stripped)
        if len(dq) % 2 == 1:
            in_dollar_quote = True
            dollar_tag = dq[-1]
            current.append(line)
            continue

        current.append(line)

        if stripped.endswith(";") and not in_dollar_quote:
            stmt = "\n".join(current).strip()
            if stmt and stmt != ";":
                statements.append(stmt)
            current = []

    remainder = "\n".join(current).strip()
    if remainder and remainder != ";":
        statements.append(remainder)

    return statements


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _run_migrations_on_startup()
    except Exception as e:
        print(f"[migrate] Startup migration error: {type(e).__name__}: {e}", flush=True)
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

app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(users_router)
app.include_router(message_template_admin_router)
app.include_router(alerts_router)
app.include_router(agent_settings_router)


# ── Health ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/v1/admin/migration-status")
async def migration_status(_: TokenPayload = Depends(require_super_admin)):
    """Diagnostic: show database migration state and environment info.

    Super-admin only. Exposes DB version, connection info, migration state,
    and DDL privilege status — treat as sensitive.
    """
    import os
    import re
    info: dict[str, Any] = {}

    admin_url = os.environ.get("DATABASE_ADMIN_URL", "")
    db_url = os.environ.get("DATABASE_URL", "")
    info["env"] = {
        "DATABASE_ADMIN_URL_set": bool(admin_url),
        "DATABASE_URL_set": bool(db_url),
    }
    info["database_url_redacted"] = re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", db_url) if db_url else ""

    try:
        async with engine.begin() as conn:
            info["connected"] = True

            ver = (await conn.execute(text("SELECT version()"))).scalar()
            info["pg_version"] = ver

            has_table = (await conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'schema_migrations')"
            ))).scalar()
            info["schema_migrations_exists"] = has_table

            if has_table:
                rows = (await conn.execute(text(
                    "SELECT version, filename, applied_at::text FROM schema_migrations ORDER BY version"
                ))).fetchall()
                info["applied_migrations"] = [{"version": r[0], "filename": r[1], "applied_at": r[2]} for r in rows]
            else:
                info["applied_migrations"] = []

            has_plan_col = (await conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'agent_runs' AND column_name = 'plan')"
            ))).scalar()
            info["agent_runs_plan_column"] = has_plan_col

            has_actions_table = (await conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'agent_plan_actions')"
            ))).scalar()
            info["agent_plan_actions_table"] = has_actions_table

            can_ddl: Any = "unknown"
            try:
                await conn.execute(text("CREATE TABLE IF NOT EXISTS _migration_ddl_test (id int)"))
                await conn.execute(text("DROP TABLE IF EXISTS _migration_ddl_test"))
                can_ddl = True
            except Exception as e:
                can_ddl = f"NO: {type(e).__name__}: {e}"
            info["can_run_ddl"] = can_ddl

    except Exception as e:
        info["connected"] = False
        info["connection_error"] = f"{type(e).__name__}: {e}"

    if info.get("can_run_ddl") and info["can_run_ddl"] is not True:
        info["fix_instructions"] = (
            "The app_user account lacks CREATE privilege on the public schema "
            "(PostgreSQL 15+ default). To fix, connect as postgres superuser and run: "
            "GRANT CREATE ON SCHEMA public TO app_user; "
            "Then also add DATABASE_ADMIN_URL to the API ECS task definition secrets "
            "for future migrations."
        )

    return info


# NOTE: The /api/v1/admin/run-migration-022 endpoint was removed as part of
# the Security Sprint. Migration 022 has shipped; an unauthenticated endpoint
# that could execute arbitrary migration SQL is a standing privilege-escalation
# risk and is unnecessary once the migration runner (deploy/db/migrate.py) is
# wired into startup. If a future manual migration is needed, run
# `python -m deploy.db.migrate` from an authenticated operator shell.


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
    tenant_id: str = ""
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
    from app_platform.api.users import effective_permissions
    return LoginUserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        permissions=effective_permissions(user.role, user.permissions),
        is_active=user.is_active,
        tenant_id=str(user.tenant_id),
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

        user_row = await session.execute(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == body.email,
                User.is_active.is_(True),
            )
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


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@app.post("/api/v1/auth/refresh", response_model=RefreshResponse)
async def refresh_token(current_user: TokenPayload = Depends(get_current_user)):
    """Issue a new access token for the current user.

    Sliding-window refresh: the caller must present a still-valid JWT, which
    is then re-signed with a fresh `exp`. If the token is already expired the
    bearer scheme rejects the request with 401 before we reach this handler,
    so the user has to log in again.

    This keeps access-token TTL short (60 min) while allowing active sessions
    to stay logged in indefinitely. The client wires a silent refresh on any
    401 before surfacing the error to the user.
    """
    async with get_tenant_session(current_user.tenant_id) as session:
        row = await session.execute(select(User).where(User.id == current_user.sub))
        user = row.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User no longer active")

    token = create_access_token(str(user.id), str(user.tenant_id), user.role)
    return RefreshResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


# ── Dashboard Metrics ────────────────────────────────────────

@app.get("/api/v1/dashboard/metrics")
async def dashboard_metrics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch: Optional[str] = None,
    employment_type: Optional[str] = None,
    employee_type: Optional[str] = None,
    legal_entity: Optional[str] = None,
    gl_segment: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Aggregated metrics for all entity panels on the main dashboard."""

    def _norm(val: Optional[str]) -> Optional[str]:
        """Treat 'All *' placeholder values and empty strings as no filter."""
        if not val or val.startswith("All "):
            return None
        return val

    branch_val = _norm(branch)
    et_val = _norm(employment_type)
    eet_val = _norm(employee_type)
    le_val = _norm(legal_entity)

    def _parse_iso_date(val: Optional[str], default: datetime.date) -> datetime.date:
        """Parse YYYY-MM-DD; reject anything else to close the SQL injection path."""
        if not val:
            return default
        try:
            return _dt.date.fromisoformat(val)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid date format; expected YYYY-MM-DD")

    today = _dt.date.today()
    df = _parse_iso_date(date_from, _dt.date(2025, 1, 1))
    dt = _parse_iso_date(date_to, today)

    tid = current_user.tenant_id

    def _i(v) -> int:
        return int(v) if v is not None else 0

    def _f(v) -> float:
        return float(v) if v is not None else 0.0

    try:
        # Build placement filter clause with bound parameters. Column names come
        # from a fixed allow-list; only the user-supplied values are bound.
        placement_filter_columns: dict[str, Optional[str]] = {
            "branch_name": branch_val,
            "employment_type": et_val,
            "employee_type": eet_val,
            "custom_text3": le_val,
        }

        p_filter_sql = "tenant_id = :tid"
        p_filter_params: dict[str, Any] = {"tid": tid}
        for col, val in placement_filter_columns.items():
            if val is not None:
                p_filter_sql += f" AND {col} = :{col}"
                p_filter_params[col] = val

        common_date_params: dict[str, Any] = {"tid": tid, "df": df, "dt": dt}

        async with get_tenant_session(tid) as session:
            # ── Placements ───────────────────────────────────────────
            p = (await session.execute(
                text(f"""
                    SELECT
                      COUNT(*) as total,
                      COUNT(*) FILTER (WHERE LOWER(status) NOT IN ('terminated','cancelled','closed')) as active,
                      COUNT(*) FILTER (WHERE LOWER(status) = 'approved') as approved,
                      COUNT(*) FILTER (WHERE LOWER(status) = 'pending') as pending,
                      COUNT(DISTINCT candidate_bullhorn_id) FILTER (WHERE LOWER(status) = 'approved') as candidates_at_approved,
                      COUNT(DISTINCT client_corporation_id) FILTER (WHERE LOWER(status) = 'approved') as customers_at_approved,
                      COUNT(*) FILTER (WHERE start_date BETWEEN :df AND :dt) as starts_in_period,
                      COUNT(*) FILTER (WHERE end_date BETWEEN :df AND :dt) as ends_in_period
                    FROM placements
                    WHERE {p_filter_sql}
                """),
                {**p_filter_params, "df": df, "dt": dt},
            )).fetchone()

            p_status = (await session.execute(
                text(f"""
                    SELECT COALESCE(status, 'Unknown') as status, COUNT(*) as cnt
                    FROM placements
                    WHERE {p_filter_sql}
                    GROUP BY status ORDER BY cnt DESC LIMIT 20
                """),
                p_filter_params,
            )).fetchall()

            # ── Timesheets ───────────────────────────────────────────
            t = (await session.execute(
                text("""
                    SELECT
                      COUNT(*) as total,
                      COUNT(*) FILTER (WHERE LOWER(approval_status) = 'approved') as approved,
                      COUNT(*) FILTER (WHERE LOWER(approval_status) = 'submitted') as submitted,
                      COUNT(*) FILTER (WHERE LOWER(approval_status) = 'rejected') as rejected,
                      COUNT(*) FILTER (WHERE LOWER(approval_status) = 'disputed') as disputed,
                      COUNT(*) FILTER (WHERE LOWER(approval_status) LIKE '%did not work%') as did_not_work,
                      COUNT(*) FILTER (WHERE LOWER(processing_status) LIKE '%btl%') as btl_failures,
                      COALESCE(SUM(hours_worked), 0) as total_hours
                    FROM timesheets
                    WHERE tenant_id = :tid
                      AND week_ending BETWEEN :df AND :dt
                """),
                common_date_params,
            )).fetchone()

            # ── Payable charges (Payroll) ────────────────────────────
            pc = (await session.execute(
                text("""
                    SELECT
                      COUNT(*) as total,
                      COUNT(*) FILTER (WHERE LOWER(status) = 'processed') as processed,
                      COUNT(*) FILTER (WHERE LOWER(status) != 'processed') as not_processed,
                      COALESCE(SUM(subtotal), 0) as total_amount,
                      COALESCE(SUM(subtotal) FILTER (WHERE LOWER(status) = 'processed'), 0) as processed_amount,
                      COALESCE(SUM(subtotal) FILTER (WHERE LOWER(status) != 'processed'), 0) as not_processed_amount
                    FROM payable_charges
                    WHERE tenant_id = :tid
                      AND period_end_date BETWEEN :df AND :dt
                """),
                common_date_params,
            )).fetchone()

            pc_status = (await session.execute(
                text("""
                    SELECT COALESCE(status, 'Unknown') as status, COUNT(*) as cnt
                    FROM payable_charges
                    WHERE tenant_id = :tid
                      AND period_end_date BETWEEN :df AND :dt
                    GROUP BY status ORDER BY cnt DESC LIMIT 20
                """),
                common_date_params,
            )).fetchall()

            # ── Billable charges (Billing) ───────────────────────────
            bc = (await session.execute(
                text("""
                    SELECT
                      COUNT(*) as total,
                      COUNT(*) FILTER (WHERE is_invoiced = true) as invoiced,
                      COUNT(*) FILTER (WHERE NOT COALESCE(is_invoiced, false)) as not_invoiced,
                      COALESCE(SUM(subtotal), 0) as total_amount,
                      COALESCE(SUM(subtotal) FILTER (WHERE is_invoiced = true), 0) as invoiced_amount,
                      COALESCE(SUM(subtotal) FILTER (WHERE NOT COALESCE(is_invoiced, false)), 0) as not_invoiced_amount
                    FROM billable_charges
                    WHERE tenant_id = :tid
                      AND period_end_date BETWEEN :df AND :dt
                """),
                common_date_params,
            )).fetchone()

            bc_status = (await session.execute(
                text("""
                    SELECT COALESCE(status, 'Unknown') as status, COUNT(*) as cnt
                    FROM billable_charges
                    WHERE tenant_id = :tid
                      AND period_end_date BETWEEN :df AND :dt
                    GROUP BY status ORDER BY cnt DESC LIMIT 20
                """),
                common_date_params,
            )).fetchall()

            # ── Invoices ─────────────────────────────────────────────
            inv = (await session.execute(
                text("""
                    SELECT
                      COUNT(*) as total,
                      COUNT(*) FILTER (WHERE COALESCE(is_finalized, false)
                                       OR LOWER(status) IN ('paid','voided','finalized')) as finalized,
                      COALESCE(SUM(balance), 0) as total_amount,
                      COALESCE(SUM(balance) FILTER (WHERE COALESCE(is_finalized, false)
                                                    OR LOWER(status) IN ('paid','voided','finalized')), 0) as finalized_amount
                    FROM invoices
                    WHERE tenant_id = :tid
                      AND invoice_date BETWEEN :df AND :dt
                """),
                common_date_params,
            )).fetchone()

            inv_status = (await session.execute(
                text("""
                    SELECT COALESCE(status, 'Unknown') as status, COUNT(*) as cnt
                    FROM invoices
                    WHERE tenant_id = :tid
                      AND invoice_date BETWEEN :df AND :dt
                    GROUP BY status ORDER BY cnt DESC LIMIT 20
                """),
                common_date_params,
            )).fetchall()

        return {
            "placements": {
                "total": _i(p.total),
                "active": _i(p.active),
                "approved": _i(p.approved),
                "pending": _i(p.pending),
                "candidates_at_approved": _i(p.candidates_at_approved),
                "customers_at_approved": _i(p.customers_at_approved),
                "starts_in_period": _i(p.starts_in_period),
                "ends_in_period": _i(p.ends_in_period),
                "by_status": {r.status: _i(r.cnt) for r in p_status},
            },
            "timesheets": {
                "total": _i(t.total),
                "approved": _i(t.approved),
                "submitted": _i(t.submitted),
                "rejected": _i(t.rejected),
                "disputed": _i(t.disputed),
                "did_not_work": _i(t.did_not_work),
                "btl_failures": _i(t.btl_failures),
                "total_hours": _f(t.total_hours),
            },
            "payroll": {
                "total": _i(pc.total),
                "processed": _i(pc.processed),
                "not_processed": _i(pc.not_processed),
                "total_amount": _f(pc.total_amount),
                "processed_amount": _f(pc.processed_amount),
                "not_processed_amount": _f(pc.not_processed_amount),
                "by_status": {r.status: _i(r.cnt) for r in pc_status},
            },
            "billing": {
                "total": _i(bc.total),
                "invoiced": _i(bc.invoiced),
                "not_invoiced": _i(bc.not_invoiced),
                "total_amount": _f(bc.total_amount),
                "invoiced_amount": _f(bc.invoiced_amount),
                "not_invoiced_amount": _f(bc.not_invoiced_amount),
                "by_status": {r.status: _i(r.cnt) for r in bc_status},
            },
            "invoices": {
                "total": _i(inv.total),
                "finalized": _i(inv.finalized),
                "not_finalized": _i(inv.total) - _i(inv.finalized),
                "total_amount": _f(inv.total_amount),
                "finalized_amount": _f(inv.finalized_amount),
                "not_finalized_amount": _f(inv.total_amount) - _f(inv.finalized_amount),
                "by_status": {r.status: _i(r.cnt) for r in inv_status},
            },
        }
    except Exception as exc:
        import traceback
        print(f"[dashboard_metrics] ERROR: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Dashboard query failed: {exc}")


# ── Dashboard Snapshot (Command Center) ─────────────────────

AGENT_TYPE_DISPLAY = {
    "vms-reconciliation": ("vms_reconciliation", "VMS Reconciliation"),
    "time-anomaly": ("time_anomaly", "Time Anomaly Detection"),
    "invoice-matching": ("invoice_matching", "Invoice Matching"),
    "forecasting": ("payment_prediction", "Payment Prediction"),
    "collections": ("collections_comms", "Collections Comms"),
    "compliance": ("compliance_monitor", "Compliance Monitor"),
    "risk-alert": ("risk_alert", "Risk Alert Agent"),
    "gl-reconciliation": ("gl_reconciliation", "GL Reconciliation"),
    "payroll-reconciliation": ("payroll_reconciliation", "Payroll Reconciliation"),
    "kpi": ("kpi", "KPI Monitor"),
    "commissions": ("commissions", "Commissions Agent"),
    "contract-compliance": ("contract_compliance", "Contract Compliance"),
}


@app.get("/api/v1/dashboard/snapshot")
async def dashboard_snapshot(current_user: TokenPayload = Depends(get_current_user)):
    """Full dashboard snapshot for the Command Center home view.

    Aggregates agent fleet status, KPIs, ROI, quality, charts, and activity
    from existing tables.  Metrics that require baseline data not yet captured
    return zero/null so the frontend can show a 'pending baseline' state.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = today_start - timedelta(days=7)

    async with get_tenant_session(current_user.tenant_id) as session:
        # ── Agent fleet status ──────────────────────────────────
        # Latest completed run per agent_type
        latest_runs_q = (
            select(
                AgentRun.agent_type,
                func.count(AgentRun.id).label("run_count_today"),
                func.avg(
                    func.extract(
                        "epoch",
                        AgentRun.completed_at - AgentRun.started_at,
                    ) * 1000
                ).label("avg_ms"),
            )
            .where(AgentRun.created_at >= today_start)
            .group_by(AgentRun.agent_type)
        )
        run_rows = (await session.execute(latest_runs_q)).all()
        run_map: dict[str, Any] = {}
        for row in run_rows:
            run_map[row.agent_type] = {
                "count": row.run_count_today or 0,
                "avg_ms": float(row.avg_ms) if row.avg_ms else 0,
            }

        # Latest status per agent type
        status_q = (
            select(AgentRun.agent_type, AgentRun.status, AgentRun.completed_at)
            .distinct(AgentRun.agent_type)
            .order_by(AgentRun.agent_type, AgentRun.created_at.desc())
        )
        status_rows = (await session.execute(status_q)).all()
        status_map: dict[str, str] = {}
        for row in status_rows:
            s = row.status
            if s in ("completed", "completed_with_errors"):
                status_map[row.agent_type] = "active"
            elif s in ("planning", "executing"):
                status_map[row.agent_type] = "processing"
            elif s == "error":
                status_map[row.agent_type] = "error"
            else:
                status_map[row.agent_type] = "idle"

        # Per-agent error counts in last 24h
        agent_errors_q = (
            select(AgentRun.agent_type, func.count(AgentRun.id).label("cnt"))
            .where(
                AgentRun.status == "error",
                AgentRun.created_at >= now - timedelta(hours=24),
            )
            .group_by(AgentRun.agent_type)
        )
        agent_error_rows = (await session.execute(agent_errors_q)).all()
        agent_error_map = {r.agent_type: r.cnt for r in agent_error_rows}

        agents_list = []
        total_txns = 0
        active_count = 0
        error_count_24h = 0

        all_types = list(AGENT_TYPE_DISPLAY.keys())
        seen_ids: set[str] = set()
        for at in all_types:
            agent_id, display_name = AGENT_TYPE_DISPLAY[at]
            if agent_id in seen_ids:
                continue
            seen_ids.add(agent_id)

            info = run_map.get(at, {"count": 0, "avg_ms": 0})
            status = status_map.get(at, "idle")
            txns = info["count"]
            total_txns += txns
            if status in ("active", "processing"):
                active_count += 1

            agent_errs = agent_error_map.get(at, 0)
            error_count_24h += agent_errs

            agents_list.append({
                "agentId": agent_id,
                "displayName": display_name,
                "status": status,
                "transactionsToday": txns,
                "accuracyRate": 0.0,
                "avgProcessingTimeMs": info["avg_ms"],
                "errorCount24h": agent_errs,
                "lastHeartbeat": now.isoformat(),
                "queueDepth": 0,
            })

        total_runs_24h = await session.scalar(
            select(func.count(AgentRun.id)).where(
                AgentRun.created_at >= now - timedelta(hours=24),
            )
        ) or 0

        error_rate = (error_count_24h / total_runs_24h * 100) if total_runs_24h > 0 else 0.0

        # Accuracy from agent_results (human override rate)
        total_reviewed = await session.scalar(
            select(func.count(AgentResult.id)).where(
                AgentResult.review_status.in_(["approved", "rejected"]),
            )
        ) or 0
        total_rejected = await session.scalar(
            select(func.count(AgentResult.id)).where(
                AgentResult.review_status == "rejected",
            )
        ) or 0
        human_override_rate = (total_rejected / total_reviewed * 100) if total_reviewed > 0 else 0.0
        first_pass_accuracy = 100 - human_override_rate if total_reviewed > 0 else 0.0

        # Auto-resolution rate from VMS matches (confidence >= 0.95, auto-accepted)
        total_matches = await session.scalar(select(func.count(VMSMatch.id))) or 0
        auto_accepted_matches = await session.scalar(
            select(func.count(VMSMatch.id)).where(
                VMSMatch.confidence >= 0.95,
                VMSMatch.status == "approved",
            )
        ) or 0
        auto_resolution_rate = round(auto_accepted_matches / total_matches * 100, 1) if total_matches > 0 else 0.0

        # Pending review queue
        pending_q = await session.scalar(
            select(func.count(AgentResult.id)).where(
                AgentResult.requires_review.is_(True),
                AgentResult.review_status == "pending",
            )
        ) or 0

        # ROI calculations from MTD agent run data
        mtd_start = today_start.replace(day=1)
        mtd_txn_rows = (await session.execute(
            select(AgentRun.result_summary).where(
                AgentRun.status.in_(["completed", "completed_with_errors"]),
                AgentRun.created_at >= mtd_start,
            )
        )).scalars().all()
        mtd_txns = sum(
            ((r or {}).get("action_count") or (r or {}).get("total_matches") or 0)
            for r in mtd_txn_rows
        )
        # Each agent transaction saves ~3 min of manual processing time
        labor_hours_saved = round(mtd_txns * 3 / 60, 1)

        # Disputes/issues caught: approved agent results this month
        disputes_prevented = await session.scalar(
            select(func.count(AgentResult.id)).where(
                AgentResult.review_status == "approved",
                AgentResult.created_at >= mtd_start,
            )
        ) or 0

        # $35/hr analyst rate + $250 avg dispute resolution cost
        mtd_cost_savings = round(labor_hours_saved * 35 + disputes_prevented * 250)
        days_elapsed = max((now - mtd_start).days, 1)
        days_in_month = 30
        projected_savings = round(mtd_cost_savings / days_elapsed * days_in_month)

        total_agents = len(agents_list)

        # Queue status
        queue_status = "normal"
        if pending_q > 100:
            queue_status = "critical"
        elif pending_q > 50:
            queue_status = "elevated"

        summary = {
            "activeAgents": active_count,
            "totalAgents": total_agents,
            "transactionsToday": total_txns,
            "transactionsTrend": 0.0,
            "mtdCostSavings": mtd_cost_savings,
            "projectedMonthlySavings": projected_savings,
            "queueDepth": pending_q,
            "queueStatus": queue_status,
            "errorRate": round(error_rate, 1),
            "errorRateTrend": 0.0,
            "lastUpdated": now.isoformat(),
        }

        roi = {
            "mtdCostSavings": mtd_cost_savings,
            "mtdCostSavingsTrend": 12.0,
            "laborHoursSaved": labor_hours_saved,
            "laborHoursTrend": 8.0,
            "disputeReduction": round(disputes_prevented * 0.3, 1),
            "disputesPrevented": disputes_prevented,
            "dsoImprovement": round(disputes_prevented * 0.3, 1),
            "cashVelocityImpact": round(mtd_cost_savings * 0.15),
            "periodStart": mtd_start.isoformat(),
            "periodEnd": now.isoformat(),
        }

        quality = {
            "firstPassAccuracy": round(first_pass_accuracy, 1),
            "autoResolutionRate": auto_resolution_rate,
            "humanOverrideRate": round(human_override_rate, 1),
            "falsePositiveRate": 0.0,
        }

        # ── Charts: transaction volume (7 days) ───────────────
        vol_q = (
            select(
                func.date(AgentRun.created_at).label("day"),
                AgentRun.agent_type,
                func.count(AgentRun.id).label("cnt"),
            )
            .where(AgentRun.created_at >= seven_days_ago)
            .group_by(func.date(AgentRun.created_at), AgentRun.agent_type)
        )
        vol_rows = (await session.execute(vol_q)).all()
        vol_by_day: dict[str, dict[str, int]] = {}
        for row in vol_rows:
            day_str = str(row.day)
            if day_str not in vol_by_day:
                vol_by_day[day_str] = {}
            agent_id = AGENT_TYPE_DISPLAY.get(row.agent_type, (row.agent_type,))[0]
            vol_by_day[day_str][agent_id] = row.cnt

        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        volume_chart = []
        for i in range(7):
            d = seven_days_ago + timedelta(days=i)
            day_str = d.strftime("%Y-%m-%d")
            day_data = vol_by_day.get(day_str, {})
            volume_chart.append({
                "date": weekdays[d.weekday()],
                "vmsReconciliation": day_data.get("vms_reconciliation", 0),
                "invoiceMatching": day_data.get("invoice_matching", 0),
                "collections": day_data.get("collections_comms", 0),
                "timeAnomaly": day_data.get("time_anomaly", 0),
            })

        # Processing time distribution
        proc_q = (
            select(
                case(
                    (func.extract("epoch", AgentRun.completed_at - AgentRun.started_at) < 1, "<1s"),
                    (func.extract("epoch", AgentRun.completed_at - AgentRun.started_at) < 2, "1-2s"),
                    (func.extract("epoch", AgentRun.completed_at - AgentRun.started_at) < 3, "2-3s"),
                    (func.extract("epoch", AgentRun.completed_at - AgentRun.started_at) < 5, "3-5s"),
                    (func.extract("epoch", AgentRun.completed_at - AgentRun.started_at) < 10, "5-10s"),
                    else_=">10s",
                ).label("bucket"),
                func.count(AgentRun.id).label("cnt"),
            )
            .where(
                AgentRun.completed_at.isnot(None),
                AgentRun.started_at.isnot(None),
            )
            .group_by("bucket")
        )
        proc_rows = (await session.execute(proc_q)).all()
        bucket_order = ["<1s", "1-2s", "2-3s", "3-5s", "5-10s", ">10s"]
        proc_map = {r.bucket: r.cnt for r in proc_rows}
        processing_chart = [
            {"bucket": b, "count": proc_map.get(b, 0)} for b in bucket_order
        ]

        # Cumulative savings — not yet tracked, return empty
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        current_month = now.month
        savings_chart = []
        for i, m in enumerate(months):
            if i + 1 <= current_month:
                savings_chart.append({"month": m, "actual": 0, "projected": None})
            else:
                savings_chart.append({"month": m, "actual": None, "projected": 0})

        # Utilization — approximated from run counts
        total_daily = max(total_txns, 1)
        util_chart = []
        for agent in agents_list:
            util_chart.append({
                "agentId": agent["agentId"],
                "displayName": agent["displayName"],
                "utilizationPercent": round(agent["transactionsToday"] / total_daily * 100, 1) if total_daily > 0 else 0,
            })

        # ── Activity feed from recent agent runs ──────────────
        recent_runs_q = (
            select(AgentRun)
            .order_by(AgentRun.created_at.desc())
            .limit(20)
        )
        recent_runs = (await session.execute(recent_runs_q)).scalars().all()

        activity_items = []
        for run in recent_runs:
            at_info = AGENT_TYPE_DISPLAY.get(run.agent_type, (run.agent_type, run.agent_type))
            agent_id = at_info[0]
            display_name = at_info[1]

            if run.status == "error":
                activity_type = "error"
                title = f"{display_name} run failed"
                detail = run.error_message or "Unknown error"
            elif run.status in ("planning", "executing"):
                activity_type = "processing"
                title = f"{display_name} processing"
                detail = f"Status: {run.status}"
            elif run.status in ("completed", "completed_with_errors"):
                activity_type = "success"
                summary_data = run.result_summary or {}
                count = summary_data.get("action_count") or summary_data.get("total_matches") or 0
                title = f"{display_name} completed"
                detail = f"{count} items processed" if count else "Run completed"
            else:
                activity_type = "processing"
                title = f"{display_name} — {run.status}"
                detail = ""

            activity_items.append({
                "id": str(run.id),
                "type": activity_type,
                "title": title,
                "agentId": agent_id,
                "agentDisplayName": display_name,
                "detail": detail,
                "timestamp": run.created_at.isoformat() if run.created_at else now.isoformat(),
            })

        # ── Action Queue: HITL items awaiting human review ──
        action_queue: dict = {"planApprovals": [], "resultReviews": [], "totalItems": 0}
        try:
            plan_approval_q = (
                select(
                    AgentRun.id,
                    AgentRun.agent_type,
                    AgentRun.created_at,
                    func.count(AgentPlanAction.id).label("action_count"),
                    func.coalesce(func.sum(AgentPlanAction.financial_impact), 0).label("total_impact"),
                    func.max(AgentPlanAction.severity).label("max_severity"),
                )
                .select_from(AgentRun)
                .join(AgentPlanAction, AgentPlanAction.run_id == AgentRun.id)
                .where(AgentRun.status == "plan_ready")
                .group_by(AgentRun.id, AgentRun.agent_type, AgentRun.created_at)
                .order_by(AgentRun.created_at.asc())
            )
            plan_rows = (await session.execute(plan_approval_q)).all()

            plan_approvals = []
            for row in plan_rows:
                at_info = AGENT_TYPE_DISPLAY.get(row.agent_type, (row.agent_type, row.agent_type))
                plan_approvals.append({
                    "runId": str(row.id),
                    "agentId": at_info[0],
                    "agentDisplayName": at_info[1],
                    "actionCount": row.action_count or 0,
                    "totalFinancialImpact": float(row.total_impact or 0),
                    "maxSeverity": row.max_severity,
                    "createdAt": row.created_at.isoformat() if row.created_at else now.isoformat(),
                })

            result_review_q = (
                select(
                    AgentRun.agent_type,
                    func.count(AgentResult.id).label("pending_count"),
                    func.coalesce(func.sum(AgentResult.financial_impact), 0).label("total_impact"),
                    func.max(AgentResult.severity).label("max_severity"),
                    func.min(AgentResult.created_at).label("oldest"),
                )
                .select_from(AgentResult)
                .join(AgentRun, AgentResult.run_id == AgentRun.id)
                .where(
                    AgentResult.requires_review.is_(True),
                    AgentResult.review_status == "pending",
                )
                .group_by(AgentRun.agent_type)
            )
            review_rows = (await session.execute(result_review_q)).all()

            result_reviews = []
            for row in review_rows:
                at_info = AGENT_TYPE_DISPLAY.get(row.agent_type, (row.agent_type, row.agent_type))
                result_reviews.append({
                    "agentId": at_info[0],
                    "agentDisplayName": at_info[1],
                    "pendingCount": row.pending_count or 0,
                    "totalFinancialImpact": float(row.total_impact or 0),
                    "maxSeverity": row.max_severity,
                    "oldestItemAt": row.oldest.isoformat() if row.oldest else now.isoformat(),
                })

            action_queue = {
                "planApprovals": plan_approvals,
                "resultReviews": result_reviews,
                "totalItems": len(plan_approvals) + sum(r["pendingCount"] for r in result_reviews),
            }
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Action queue query failed — returning empty queue")

        return {
            "summary": summary,
            "agents": agents_list,
            "roi": roi,
            "quality": quality,
            "charts": {
                "transactionVolume": volume_chart,
                "processingTime": processing_chart,
                "cumulativeSavings": savings_chart,
                "utilization": util_chart,
            },
            "recentActivity": activity_items,
            "actionQueue": action_queue,
            "generatedAt": now.isoformat(),
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


# ── Tenant Settings ───────────────────────────────────────────

DEFAULT_RISK_SETTINGS: dict = {
    "approvedStatuses":    "Active, Confirmed, In Progress, Working",
    "pendingStatuses":     "Draft, Onboarding, Pending Start, Under Review",
    "inactiveStatuses":    "Closed, Ended, Terminated, Cancelled",
    "belowFederalMinWage": 7.25,
    "highPayRate":         150.0,
    "highBillRate":        225.0,
    "highHours":           60.0,
    "highPayAmounts":      5000.0,
    "highBillAmounts":     7500.0,
    "lowMarkup":           10.0,
    "highMarkup":          250.0,
    "billRateMismatchPct": 20.0,
}


class TenantSettingsUpdate(BaseModel):
    riskTolerances: dict
    userAccess: dict | None = None


async def _get_tenant_settings(session, tenant_id: str) -> dict:
    """Load tenant settings JSONB, merging with defaults."""
    row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = row.scalar_one_or_none()
    if not tenant or not tenant.settings:
        return {"riskTolerances": DEFAULT_RISK_SETTINGS, "userAccess": {}}
    stored = tenant.settings
    # Merge risk tolerances with defaults so new keys always have a value
    rt = {**DEFAULT_RISK_SETTINGS, **(stored.get("riskTolerances") or {})}
    return {
        "riskTolerances": rt,
        "userAccess": stored.get("userAccess") or {},
    }


@app.get("/api/v1/settings")
async def get_settings(current_user: TokenPayload = Depends(get_current_user)):
    async with get_tenant_session(current_user.tenant_id) as session:
        return await _get_tenant_settings(session, current_user.tenant_id)


@app.put("/api/v1/settings")
async def put_settings(
    body: TenantSettingsUpdate,
    current_user: TokenPayload = Depends(get_current_user),
):
    if current_user.role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin role required")
    async with get_tenant_session(current_user.tenant_id) as session:
        row = await session.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
        tenant = row.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        existing = tenant.settings or {}
        tenant.settings = {
            **existing,
            "riskTolerances": body.riskTolerances,
            **({"userAccess": body.userAccess} if body.userAccess is not None else {}),
        }
        from sqlalchemy import update as sa_update
        await session.execute(
            sa_update(Tenant)
            .where(Tenant.id == current_user.tenant_id)
            .values(settings=tenant.settings)
        )
    return {"ok": True}


# ── TimeOps ───────────────────────────────────────────────────

def _last_sunday(ref: _dt.date | None = None) -> _dt.date:
    """Return the most recent Sunday on or before ref (default: today)."""
    d = ref or _dt.date.today()
    return d - _dt.timedelta(days=(d.weekday() + 1) % 7)


class TimeOpsRecordUpdate(BaseModel):
    is_excluded: bool | None = None
    comments: str | None = None
    send_reminder: bool = False


@app.get("/api/v1/timeops/records")
async def timeops_records(
    period_end: str | None = None,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Return active placements with no submitted timesheet for the given period."""
    try:
        if period_end:
            period = _dt.date.fromisoformat(period_end)
        else:
            period = _last_sunday()

        sql = text("""
            SELECT
                p.id::text                                                        AS record_id,
                p.bullhorn_id                                                     AS placement_bullhorn_id,
                COALESCE(p.client_corporation_name, p.client_name, '')            AS customer_name,
                COALESCE(p.job_title, '')                                         AS job_title,
                COALESCE(
                    p.candidate_name,
                    NULLIF(TRIM(CONCAT(p.candidate_first, ' ', p.candidate_last)), ''),
                    ''
                )                                                                 AS candidate_name,
                COALESCE(c.email, '')                                             AS candidate_email,
                p.start_date,
                p.end_date,
                COALESCE(p.branch_name, '')                                       AS branch,
                COALESCE(te.is_excluded, FALSE)                                   AS is_excluded,
                COALESCE(te.excluded_by, '')                                      AS excluded_by,
                te.excluded_at,
                te.last_reminder_sent_at,
                COALESCE(te.comments, '')                                         AS comments
            FROM placements p
            LEFT JOIN candidates c
                ON  c.tenant_id    = p.tenant_id
                AND c.bullhorn_id  = p.candidate_bullhorn_id
            LEFT JOIN timeops_exclusions te
                ON  te.tenant_id              = p.tenant_id
                AND te.placement_bullhorn_id  = p.bullhorn_id
                AND te.period_end_date        = :period
            LEFT JOIN timesheets t
                ON  t.placement_id  = p.id
                AND t.week_ending   = :period
                AND LOWER(COALESCE(t.status, '')) NOT IN ('rejected', 'deleted')
            WHERE p.tenant_id = :tid
              AND LOWER(COALESCE(p.status, '')) NOT IN ('terminated', 'completed', 'declined', 'inactive')
              AND p.start_date <= :period
              AND (p.end_date IS NULL OR p.end_date >= :period - INTERVAL '14 days')
              AND t.id IS NULL
            ORDER BY customer_name, candidate_name
            LIMIT 500
        """)

        async with get_tenant_session(current_user.tenant_id) as session:
            rows = await session.execute(sql, {"tid": current_user.tenant_id, "period": period})
            records = rows.mappings().all()

        def _fmt_date(d) -> str:
            if d is None:
                return "—"
            if isinstance(d, (datetime.date, datetime.datetime)):
                return d.strftime("%m/%d/%Y")
            return str(d)

        def _fmt_ts(d) -> str:
            if d is None:
                return "—"
            if isinstance(d, datetime.datetime):
                return d.strftime("%m/%d/%Y %I:%M %p")
            return _fmt_date(d)

        result = []
        for i, r in enumerate(records):
            result.append({
                "id": i + 1,
                "timesheetId": f"MISSING-{r['placement_bullhorn_id']}",
                "excluded": r["is_excluded"],
                "excludedBy": r["excluded_by"] or "—",
                "excludedDate": _fmt_ts(r["excluded_at"]),
                "lastReminderSent": _fmt_date(r["last_reminder_sent_at"]),
                "placementId": r["placement_bullhorn_id"],
                "customerName": r["customer_name"],
                "jobTitle": r["job_title"],
                "candidateName": r["candidate_name"],
                "placementStart": _fmt_date(r["start_date"]),
                "placementEnd": _fmt_date(r["end_date"]),
                "periodEndDate": period.strftime("%m/%d/%Y"),
                "candidateEmail": r["candidate_email"],
                "comments": r["comments"],
                "branch": r["branch"],
            })
        return {"records": result, "period_end": period.isoformat()}

    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        print(f"[timeops_records] ERROR: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"TimeOps query failed: {exc}")


@app.patch("/api/v1/timeops/records/{placement_bullhorn_id}")
async def update_timeops_record(
    placement_bullhorn_id: str,
    body: TimeOpsRecordUpdate,
    period_end: str | None = None,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Upsert exclusion/reminder state for a placement in a given period."""
    try:
        period = _dt.date.fromisoformat(period_end) if period_end else _last_sunday()
        now = datetime.now(timezone.utc)

        upsert_sql = text("""
            INSERT INTO timeops_exclusions
                (tenant_id, placement_bullhorn_id, period_end_date,
                 is_excluded, excluded_by, excluded_at,
                 last_reminder_sent_at, comments, updated_at)
            VALUES
                (:tid, :pid, :period,
                 COALESCE(:is_excluded, FALSE), :excluded_by,
                 CASE WHEN :is_excluded IS TRUE THEN :now ELSE NULL END,
                 CASE WHEN :send_reminder THEN :now ELSE NULL END,
                 COALESCE(:comments, ''), :now)
            ON CONFLICT (tenant_id, placement_bullhorn_id, period_end_date) DO UPDATE SET
                is_excluded           = COALESCE(:is_excluded, timeops_exclusions.is_excluded),
                excluded_by           = CASE WHEN :is_excluded IS NOT NULL
                                             THEN :excluded_by
                                             ELSE timeops_exclusions.excluded_by END,
                excluded_at           = CASE WHEN :is_excluded IS TRUE THEN :now
                                             WHEN :is_excluded IS FALSE THEN NULL
                                             ELSE timeops_exclusions.excluded_at END,
                last_reminder_sent_at = CASE WHEN :send_reminder
                                             THEN :now
                                             ELSE timeops_exclusions.last_reminder_sent_at END,
                comments              = COALESCE(:comments, timeops_exclusions.comments),
                updated_at            = :now
        """)

        user_name = current_user.sub

        async with get_tenant_session(current_user.tenant_id) as session:
            await session.execute(upsert_sql, {
                "tid": current_user.tenant_id,
                "pid": placement_bullhorn_id,
                "period": period,
                "is_excluded": body.is_excluded,
                "excluded_by": user_name,
                "send_reminder": body.send_reminder,
                "comments": body.comments,
                "now": now,
            })

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        print(f"[update_timeops_record] ERROR: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(exc))


# ── RiskOps ───────────────────────────────────────────────────

_RISK_CATEGORY_META: dict[str, dict] = {
    "missing-timesheets": {"label": "Missing Timesheets",   "severity": "CRT", "color": "#7c3aed",
                           "subs": [{"label": "No Timesheet Submitted", "errorType": "no-ts"}]},
    "hours-flags":        {"label": "Hours Flags",           "severity": "MED", "color": "#d97706",
                           "subs": [{"label": "Excessive Hours (>60/wk)", "errorType": "excessive-hours"},
                                    {"label": "Zero Hours Submitted",     "errorType": "zero-hours"}]},
    "markup-analysis":    {"label": "Markup Analysis",       "severity": "LOW", "color": "#0891b2",
                           "subs": [{"label": "Low Markup (<10%)",        "errorType": "low-markup"},
                                    {"label": "High Markup (>250%)",      "errorType": "high-markup"}]},
    "placement-alignment":{"label": "Placement Alignment",   "severity": "HIGH","color": "#dc2626",
                           "subs": [{"label": "Bill Rate Mismatch",       "errorType": "bill-rate-mismatch"},
                                    {"label": "Pay Rate Mismatch",        "errorType": "pay-rate-mismatch"}]},
    "rate-flags":         {"label": "Rate Flags",            "severity": "MED", "color": "#ea580c",
                           "subs": [{"label": "High Pay Rate",            "errorType": "high-pay-rate"},
                                    {"label": "High Bill Rate",           "errorType": "high-bill-rate"}]},
    "wage-compliance":    {"label": "Wage Compliance",       "severity": "HIGH","color": "#be123c",
                           "subs": [{"label": "Below Federal Min Wage",   "errorType": "below-min-wage"}]},
    "amounts-flags":      {"label": "Amounts Flags",         "severity": "LOW", "color": "#65a30d",
                           "subs": [{"label": "High Pay Amount",          "errorType": "high-pay-amount"},
                                    {"label": "High Bill Amount",         "errorType": "high-bill-amount"}]},
}

_RISK_SQL = text("""
WITH
hours_flags AS (
    SELECT
        'hours-flags:ts:' || t.id::text                                   AS record_key,
        COALESCE(t.bullhorn_id, 'TS-' || t.id::text)                     AS timesheet_id,
        'hours-flags'                                                      AS category,
        CASE WHEN (COALESCE(t.regular_hours,0)+COALESCE(t.ot_hours,0)) = 0
             THEN 'zero-hours' ELSE 'excessive-hours' END                 AS error_type,
        CASE WHEN (COALESCE(t.regular_hours,0)+COALESCE(t.ot_hours,0)) = 0
             THEN 'MED' ELSE 'HIGH' END                                   AS severity,
        COALESCE(p.client_corporation_name, p.client_name, '')            AS customer_name,
        COALESCE(t.candidate_name, p.candidate_name,
            NULLIF(TRIM(CONCAT(p.candidate_first,' ',p.candidate_last)),''), '') AS candidate_name,
        COALESCE(p.bullhorn_id, '')                                        AS placement_bullhorn_id,
        t.week_ending                                                      AS ts_period,
        COALESCE(t.regular_hours,0) + COALESCE(t.ot_hours,0)             AS hours_worked,
        COALESCE(t.regular_hours,0)                                        AS pay_hours,
        COALESCE(t.ot_hours,0)                                             AS bill_hours,
        COALESCE(p.pay_rate,0)                                             AS pay_rate,
        COALESCE(COALESCE(t.bill_rate, p.bill_rate), 0)                   AS bill_rate,
        COALESCE(p.mark_up_percentage,0)                                   AS markup_pct,
        COALESCE(p.branch_name,'')                                         AS branch
    FROM timesheets t
    LEFT JOIN placements p ON p.id = t.placement_id AND p.tenant_id = t.tenant_id
    WHERE t.tenant_id = :tid
      AND t.week_ending >= CURRENT_DATE - INTERVAL '90 days'
      AND (
          (COALESCE(t.regular_hours,0) + COALESCE(t.ot_hours,0)) > :high_hours
          OR
          (COALESCE(t.regular_hours,0) + COALESCE(t.ot_hours,0)) = 0
      )
),
markup_flags AS (
    SELECT
        'markup-analysis:p:' || p.id::text                               AS record_key,
        'PLACE-' || p.bullhorn_id                                         AS timesheet_id,
        'markup-analysis'                                                  AS category,
        CASE WHEN p.mark_up_percentage < :low_markup THEN 'low-markup'
             ELSE 'high-markup' END                                        AS error_type,
        'LOW'                                                              AS severity,
        COALESCE(p.client_corporation_name, p.client_name, '')            AS customer_name,
        COALESCE(
            p.candidate_name,
            NULLIF(TRIM(CONCAT(p.candidate_first,' ',p.candidate_last)),''), '') AS candidate_name,
        p.bullhorn_id                                                      AS placement_bullhorn_id,
        p.start_date                                                       AS ts_period,
        0.0                                                                AS hours_worked,
        0.0                                                                AS pay_hours,
        0.0                                                                AS bill_hours,
        COALESCE(p.pay_rate,0)                                             AS pay_rate,
        COALESCE(p.bill_rate,0)                                            AS bill_rate,
        p.mark_up_percentage                                               AS markup_pct,
        COALESCE(p.branch_name,'')                                         AS branch
    FROM placements p
    WHERE p.tenant_id = :tid
      AND p.pay_rate IS NOT NULL AND p.pay_rate > 0
      AND p.bill_rate IS NOT NULL AND p.bill_rate > 0
      AND p.mark_up_percentage IS NOT NULL
      AND (p.mark_up_percentage < :low_markup OR p.mark_up_percentage > :high_markup)
      AND LOWER(COALESCE(p.status,'')) NOT IN ('terminated','completed','declined','inactive')
),
alignment_flags AS (
    SELECT
        'placement-alignment:ts:' || t.id::text                           AS record_key,
        COALESCE(t.bullhorn_id, 'TS-' || t.id::text)                     AS timesheet_id,
        'placement-alignment'                                              AS category,
        'bill-rate-mismatch'                                               AS error_type,
        'HIGH'                                                             AS severity,
        COALESCE(p.client_corporation_name, p.client_name, '')            AS customer_name,
        COALESCE(t.candidate_name, p.candidate_name,
            NULLIF(TRIM(CONCAT(p.candidate_first,' ',p.candidate_last)),''), '') AS candidate_name,
        COALESCE(p.bullhorn_id, '')                                        AS placement_bullhorn_id,
        t.week_ending                                                      AS ts_period,
        COALESCE(t.regular_hours,0) + COALESCE(t.ot_hours,0)             AS hours_worked,
        COALESCE(t.regular_hours,0)                                        AS pay_hours,
        COALESCE(t.ot_hours,0)                                             AS bill_hours,
        COALESCE(p.pay_rate,0)                                             AS pay_rate,
        COALESCE(t.bill_rate,0)                                            AS bill_rate,
        COALESCE(p.mark_up_percentage,0)                                   AS markup_pct,
        COALESCE(p.branch_name,'')                                         AS branch
    FROM timesheets t
    INNER JOIN placements p ON p.id = t.placement_id AND p.tenant_id = t.tenant_id
    WHERE t.tenant_id = :tid
      AND t.week_ending >= CURRENT_DATE - INTERVAL '90 days'
      AND t.bill_rate IS NOT NULL
      AND p.bill_rate IS NOT NULL AND p.bill_rate > 0
      AND ABS(t.bill_rate - p.bill_rate) / p.bill_rate > (:bill_rate_mismatch_pct / 100.0)
),
wage_flags AS (
    SELECT
        'wage-compliance:p:' || p.id::text                               AS record_key,
        'PLACE-' || p.bullhorn_id                                         AS timesheet_id,
        'wage-compliance'                                                  AS category,
        'below-min-wage'                                                   AS error_type,
        'HIGH'                                                             AS severity,
        COALESCE(p.client_corporation_name, p.client_name, '')            AS customer_name,
        COALESCE(
            p.candidate_name,
            NULLIF(TRIM(CONCAT(p.candidate_first,' ',p.candidate_last)),''), '') AS candidate_name,
        p.bullhorn_id                                                      AS placement_bullhorn_id,
        p.start_date                                                       AS ts_period,
        0.0                                                                AS hours_worked,
        0.0                                                                AS pay_hours,
        0.0                                                                AS bill_hours,
        COALESCE(p.pay_rate,0)                                             AS pay_rate,
        COALESCE(p.bill_rate,0)                                            AS bill_rate,
        COALESCE(p.mark_up_percentage,0)                                   AS markup_pct,
        COALESCE(p.branch_name,'')                                         AS branch
    FROM placements p
    WHERE p.tenant_id = :tid
      AND p.pay_rate IS NOT NULL
      AND p.pay_rate < :min_wage
      AND LOWER(COALESCE(p.status,'')) NOT IN ('terminated','completed','declined','inactive')
),
all_flags AS (
    SELECT * FROM hours_flags
    UNION ALL SELECT * FROM markup_flags
    UNION ALL SELECT * FROM alignment_flags
    UNION ALL SELECT * FROM wage_flags
)
SELECT
    f.*,
    COALESCE(rr.status,  'Open')  AS resolution_status,
    COALESCE(rr.resolved_by, '')  AS resolved_by,
    rr.resolved_at,
    COALESCE(rr.comments, '')     AS resolution_comments
FROM all_flags f
LEFT JOIN riskops_resolutions rr
    ON  rr.tenant_id  = :tid
    AND rr.record_key = f.record_key
ORDER BY f.category, f.ts_period DESC NULLS LAST
LIMIT 1000
""")


def _risk_sql_params(tid: str, rt: dict) -> dict:
    return {
        "tid": tid,
        "high_hours":           float(rt.get("highHours", DEFAULT_RISK_SETTINGS["highHours"])),
        "low_markup":           float(rt.get("lowMarkup",  DEFAULT_RISK_SETTINGS["lowMarkup"])),
        "high_markup":          float(rt.get("highMarkup", DEFAULT_RISK_SETTINGS["highMarkup"])),
        "bill_rate_mismatch_pct": float(rt.get("billRateMismatchPct", DEFAULT_RISK_SETTINGS["billRateMismatchPct"])),
        "min_wage":             float(rt.get("belowFederalMinWage", DEFAULT_RISK_SETTINGS["belowFederalMinWage"])),
    }


@app.get("/api/v1/riskops/records")
async def riskops_records(
    current_user: TokenPayload = Depends(get_current_user),
):
    """Compute risk alert records from real placement/timesheet data."""
    try:
        async with get_tenant_session(current_user.tenant_id) as session:
            cfg = await _get_tenant_settings(session, current_user.tenant_id)
            rt = cfg["riskTolerances"]
            rows = await session.execute(_RISK_SQL, _risk_sql_params(current_user.tenant_id, rt))
            records = rows.mappings().all()

        def _fmt_date(d) -> str:
            if d is None:
                return "—"
            if isinstance(d, (datetime.date, datetime.datetime)):
                return d.strftime("%m/%d/%Y")
            return str(d)

        def _fmt_ts(d) -> str:
            if d is None:
                return "—"
            if isinstance(d, datetime.datetime):
                return d.strftime("%m/%d/%Y %I:%M %p")
            return _fmt_date(d)

        def _fmt_money(rate, hours) -> str:
            if not rate or not hours:
                return "—"
            return f"${float(rate) * float(hours):,.2f}"

        def _fmt_pct(v) -> str:
            if v is None:
                return "—"
            return f"{float(v):.1f}%"

        result = []
        for i, r in enumerate(records):
            pay_rate = float(r["pay_rate"] or 0)
            bill_rate = float(r["bill_rate"] or 0)
            hours = float(r["hours_worked"] or 0)
            result.append({
                "id": i + 1,
                "timesheetId": r["timesheet_id"] or f"REC-{i+1}",
                "resolvedStatus": r["resolution_status"],
                "category": r["category"],
                "errorType": _RISK_CATEGORY_META.get(r["category"], {}).get("subs", [{}])[0].get("label", r["error_type"]),
                "customerName": r["customer_name"],
                "candidateName": r["candidate_name"],
                "placementId": r["placement_bullhorn_id"],
                "tsPeriod": _fmt_date(r["ts_period"]),
                "hoursWorked": hours,
                "payHours": float(r["pay_hours"] or 0),
                "billHours": float(r["bill_hours"] or 0),
                "paid": _fmt_money(pay_rate, hours) if hours else ("$" + f"{pay_rate:.2f}/hr" if pay_rate else "—"),
                "billed": _fmt_money(bill_rate, hours) if hours else ("$" + f"{bill_rate:.2f}/hr" if bill_rate else "—"),
                "markupPct": _fmt_pct(r["markup_pct"]),
                "comments": r["resolution_comments"],
                "resolvedBy": r["resolved_by"] or "—",
                "resolvedDate": _fmt_ts(r["resolved_at"]),
                "severity": _RISK_CATEGORY_META.get(r["category"], {}).get("severity", "MED"),
                "branch": r["branch"],
            })
        return {"records": result}

    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        print(f"[riskops_records] ERROR: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"RiskOps query failed: {exc}")


@app.get("/api/v1/riskops/categories")
async def riskops_categories(
    current_user: TokenPayload = Depends(get_current_user),
):
    """Return risk category counts from real data."""
    try:
        counts_sql = text("""
            WITH
            hours_flags AS (
                SELECT 'hours-flags' AS cat,
                    CASE WHEN (COALESCE(regular_hours,0)+COALESCE(ot_hours,0)) = 0
                         THEN 'zero-hours' ELSE 'excessive-hours' END AS sub
                FROM timesheets
                WHERE tenant_id = :tid
                  AND week_ending >= CURRENT_DATE - INTERVAL '90 days'
                  AND (
                      (COALESCE(regular_hours,0)+COALESCE(ot_hours,0)) > :high_hours
                      OR (COALESCE(regular_hours,0)+COALESCE(ot_hours,0)) = 0
                  )
            ),
            markup_flags AS (
                SELECT 'markup-analysis' AS cat,
                    CASE WHEN mark_up_percentage < :low_markup THEN 'low-markup' ELSE 'high-markup' END AS sub
                FROM placements
                WHERE tenant_id = :tid
                  AND pay_rate > 0 AND bill_rate > 0
                  AND mark_up_percentage IS NOT NULL
                  AND (mark_up_percentage < :low_markup OR mark_up_percentage > :high_markup)
                  AND LOWER(COALESCE(status,'')) NOT IN ('terminated','completed','declined','inactive')
            ),
            alignment_flags AS (
                SELECT 'placement-alignment' AS cat, 'bill-rate-mismatch' AS sub
                FROM timesheets t
                INNER JOIN placements p ON p.id = t.placement_id AND p.tenant_id = t.tenant_id
                WHERE t.tenant_id = :tid
                  AND t.week_ending >= CURRENT_DATE - INTERVAL '90 days'
                  AND t.bill_rate IS NOT NULL
                  AND p.bill_rate IS NOT NULL AND p.bill_rate > 0
                  AND ABS(t.bill_rate - p.bill_rate) / p.bill_rate > (:bill_rate_mismatch_pct / 100.0)
            ),
            wage_flags AS (
                SELECT 'wage-compliance' AS cat, 'below-min-wage' AS sub
                FROM placements
                WHERE tenant_id = :tid
                  AND pay_rate IS NOT NULL AND pay_rate < :min_wage
                  AND LOWER(COALESCE(status,'')) NOT IN ('terminated','completed','declined','inactive')
            ),
            all_flags AS (
                SELECT * FROM hours_flags
                UNION ALL SELECT * FROM markup_flags
                UNION ALL SELECT * FROM alignment_flags
                UNION ALL SELECT * FROM wage_flags
            )
            SELECT cat, sub, COUNT(*) AS cnt
            FROM all_flags
            GROUP BY cat, sub
        """)

        async with get_tenant_session(current_user.tenant_id) as session:
            cfg = await _get_tenant_settings(session, current_user.tenant_id)
            rt = cfg["riskTolerances"]
            rows = await session.execute(counts_sql, _risk_sql_params(current_user.tenant_id, rt))
            raw = rows.mappings().all()

        # Build category + subcategory count map
        cat_counts: dict[str, int] = {}
        sub_counts: dict[str, dict[str, int]] = {}
        for r in raw:
            cat = r["cat"]
            sub = r["sub"]
            cnt = int(r["cnt"])
            cat_counts[cat] = cat_counts.get(cat, 0) + cnt
            sub_counts.setdefault(cat, {})[sub] = cnt

        result = []
        for cat_id, meta in _RISK_CATEGORY_META.items():
            subs_out = []
            for s in meta.get("subs", []):
                et = s["errorType"]
                subs_out.append({
                    "label": s["label"],
                    "count": sub_counts.get(cat_id, {}).get(et, 0),
                    "errorType": et,
                })
            result.append({
                "id": cat_id,
                "label": meta["label"],
                "count": cat_counts.get(cat_id, 0),
                "severity": meta["severity"],
                "color": meta["color"],
                "subCategories": subs_out,
            })
        return {"categories": result}

    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        print(f"[riskops_categories] ERROR: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"RiskOps categories failed: {exc}")


class RiskOpsRecordUpdate(BaseModel):
    status: str  # Open | Pending | Resolved
    comments: str | None = None


@app.patch("/api/v1/riskops/records/{record_key:path}")
async def update_riskops_record(
    record_key: str,
    body: RiskOpsRecordUpdate,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Upsert resolution state for a risk record."""
    try:
        now = datetime.now(timezone.utc)
        user_name = current_user.sub

        upsert_sql = text("""
            INSERT INTO riskops_resolutions
                (tenant_id, record_key, status, resolved_by, resolved_at, comments, updated_at)
            VALUES
                (:tid, :key, :status, :user,
                 CASE WHEN :status != 'Open' THEN :now ELSE NULL END,
                 COALESCE(:comments, ''), :now)
            ON CONFLICT (tenant_id, record_key) DO UPDATE SET
                status      = :status,
                resolved_by = :user,
                resolved_at = CASE WHEN :status != 'Open' THEN :now
                                   ELSE NULL END,
                comments    = COALESCE(:comments, riskops_resolutions.comments),
                updated_at  = :now
        """)

        async with get_tenant_session(current_user.tenant_id) as session:
            await session.execute(upsert_sql, {
                "tid": current_user.tenant_id,
                "key": record_key,
                "status": body.status,
                "user": user_name,
                "comments": body.comments,
                "now": now,
            })

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        print(f"[update_riskops_record] ERROR: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(exc))


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
            import asyncio as _asyncio
            graph = get_graph()
            graph_input = {
                "tenant_id": current_user.tenant_id,
                "vms_records": vms_records,
                "placements": placements,
                "aliases": aliases,
            }
            result = await _asyncio.to_thread(graph.invoke, graph_input)
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


# ── Agent Plan-Approve-Execute Cycle ─────────────────────────

AGENT_TYPE_REGISTRY: dict[str, str] = {
    "vms-reconciliation": "src.agents.vms_reconciliation.graph",
    "time-anomaly": "src.agents.time_anomaly.graph",
    "invoice-matching": "src.agents.invoice_matching.graph",
    "collections": "src.agents.collections.graph",
    "compliance": "src.agents.compliance.graph",
    "risk-alert": "src.agents.risk_alert.graph",
    "gl-reconciliation": "src.agents.gl_reconciliation.graph",
    "payroll-reconciliation": "src.agents.payroll_reconciliation.graph",
    "forecasting": "src.agents.forecasting.graph",
    "kpi": "src.agents.kpi.graph",
    "commissions": "src.agents.commissions.graph",
    "contract-compliance": "src.agents.contract_compliance.graph",
}


class PlanRequest(BaseModel):
    weeks_back: int = 8
    upload_id: str | None = None
    config: dict[str, Any] | None = None


class ApproveRequest(BaseModel):
    action_ids: list[str] | None = None


@app.post("/api/v1/agents/{agent_type}/plan")
async def create_agent_plan(
    agent_type: str,
    body: PlanRequest | None = None,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Phase 1: trigger planning. Agent analyzes data and produces a plan with proposed actions."""
    from datetime import datetime, timedelta, timezone

    if body is None:
        body = PlanRequest()

    if agent_type not in AGENT_TYPE_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown agent type: {agent_type}")

    async with get_tenant_session(current_user.tenant_id) as session:
        # Tier Enforcement check
        tenant = await session.get(Tenant, uuid.UUID(current_user.tenant_id))
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Map URL agent_type (hyphenated) to AgentId (underscored)
        internal_id = agent_type.replace("-", "_")
        verify_tier_access(tenant.tier, internal_id)

        run = AgentRun(
            tenant_id=uuid.UUID(current_user.tenant_id),
            agent_type=agent_type,
            status="planning",
            triggered_by=uuid.UUID(current_user.sub),
            trigger_type="manual",
            config=body.config or {},
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        try:
            await session.flush()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Database error creating agent run. The agent_runs table may need migration (plan, execution_report, approved_by, approved_at columns). Detail: {e}",
            )

        # Load data based on agent type
        plan_actions: list[dict[str, Any]] = []
        plan_summary: dict[str, Any] = {}
        token_usage = None

        try:
            if agent_type == "vms-reconciliation":
                plan_actions, plan_summary, token_usage = await _plan_vms_match(
                    session, current_user.tenant_id, body.weeks_back, body.upload_id,
                )
            elif agent_type == "time-anomaly":
                plan_actions, plan_summary, token_usage = await _plan_time_anomaly(
                    session, current_user.tenant_id,
                )
            elif agent_type == "invoice-matching":
                plan_actions, plan_summary, token_usage = await _plan_invoice_matching(
                    session, current_user.tenant_id,
                )
            elif agent_type == "collections":
                plan_actions, plan_summary, token_usage = await _plan_collections(
                    session, current_user.tenant_id,
                )
            elif agent_type == "compliance":
                plan_actions, plan_summary, token_usage = await _plan_compliance(
                    session, current_user.tenant_id,
                )
            elif agent_type == "risk-alert":
                plan_actions, plan_summary, token_usage = await _plan_risk_alert(
                    session, current_user.tenant_id,
                )
            elif agent_type == "gl-reconciliation":
                plan_actions, plan_summary, token_usage = await _plan_gl_reconciliation(
                    session, current_user.tenant_id,
                )
            elif agent_type == "payroll-reconciliation":
                plan_actions, plan_summary, token_usage = await _plan_payroll_reconciliation(
                    session, current_user.tenant_id,
                )
            elif agent_type == "forecasting":
                plan_actions, plan_summary, token_usage = await _plan_forecasting(
                    session, current_user.tenant_id,
                )
            elif agent_type == "kpi":
                plan_actions, plan_summary, token_usage = await _plan_kpi(
                    session, current_user.tenant_id,
                )
            elif agent_type == "commissions":
                plan_actions, plan_summary, token_usage = await _plan_commissions(
                    session, current_user.tenant_id,
                )
            elif agent_type == "contract-compliance":
                plan_actions, plan_summary, token_usage = await _plan_contract_compliance(
                    session, current_user.tenant_id,
                )
            else:
                raise HTTPException(status_code=400, detail=f"Planning not implemented for {agent_type}")
        except HTTPException:
            raise
        except Exception as e:
            run.status = "error"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            return {"run_id": str(run.id), "status": "error", "error": str(e)}

        def _jsonable(obj: Any) -> Any:
            """Recursively convert Decimal/non-JSON-serializable types."""
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, dict):
                return {k: _jsonable(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_jsonable(v) for v in obj]
            return obj

        # Persist plan actions
        for pa in plan_actions:
            action = AgentPlanAction(
                run_id=run.id,
                action_type=pa["action_type"],
                target_ref=pa.get("target_ref"),
                target_name=pa.get("target_name"),
                description=pa["description"],
                confidence=float(pa["confidence"]) if pa.get("confidence") is not None else None,
                severity=pa.get("severity"),
                financial_impact=float(pa["financial_impact"]) if pa.get("financial_impact") is not None else None,
                details=_jsonable(pa.get("details")),
            )
            session.add(action)

        run.status = "plan_ready"
        run.plan = plan_summary
        run.token_usage = token_usage
        try:
            await session.flush()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Database error saving plan. The agent_plan_actions table may need to be created. Detail: {e}",
            )

    return {
        "run_id": str(run.id),
        "status": "plan_ready",
        "summary": plan_summary,
        "action_count": len(plan_actions),
    }


@app.get("/api/v1/agents/runs/{run_id}/plan")
async def get_agent_plan(
    run_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Fetch the plan for a run: run metadata + all proposed actions."""
    async with get_tenant_session(current_user.tenant_id) as session:
        run = await session.get(AgentRun, uuid.UUID(run_id))
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        actions_q = (
            select(AgentPlanAction)
            .where(AgentPlanAction.run_id == uuid.UUID(run_id))
            .order_by(AgentPlanAction.confidence.asc().nullslast())
        )
        rows = (await session.execute(actions_q)).scalars().all()

        return {
            "run": _row_to_dict(run),
            "actions": [_row_to_dict(a) for a in rows],
        }


@app.post("/api/v1/agents/runs/{run_id}/approve")
async def approve_agent_plan(
    run_id: str,
    body: ApproveRequest | None = None,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Approve the plan (all actions or a subset). Transitions run to 'approved'."""
    from datetime import datetime, timezone

    if body is None:
        body = ApproveRequest()

    async with get_tenant_session(current_user.tenant_id) as session:
        run = await session.get(AgentRun, uuid.UUID(run_id))
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.status not in ("plan_ready",):
            raise HTTPException(status_code=409, detail=f"Run is in '{run.status}' state, cannot approve")

        actions_q = select(AgentPlanAction).where(AgentPlanAction.run_id == uuid.UUID(run_id))
        rows = (await session.execute(actions_q)).scalars().all()

        if body.action_ids:
            approved_set = set(body.action_ids)
            for a in rows:
                if str(a.id) in approved_set:
                    a.approval_status = "approved"
                else:
                    a.approval_status = "skipped"
        else:
            for a in rows:
                a.approval_status = "approved"

        run.status = "approved"
        run.approved_by = uuid.UUID(current_user.sub)
        run.approved_at = datetime.now(timezone.utc)

    return {"run_id": run_id, "status": "approved", "approved_count": sum(1 for a in rows if a.approval_status == "approved")}


@app.post("/api/v1/agents/runs/{run_id}/execute")
async def execute_agent_plan(
    run_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Phase 2: execute all approved actions and produce an execution report."""
    from datetime import datetime, timezone

    async with get_tenant_session(current_user.tenant_id) as session:
        run = await session.get(AgentRun, uuid.UUID(run_id))
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.status not in ("approved",):
            raise HTTPException(status_code=409, detail=f"Run is in '{run.status}' state, cannot execute")

        run.status = "executing"
        await session.flush()

        actions_q = (
            select(AgentPlanAction)
            .where(AgentPlanAction.run_id == uuid.UUID(run_id))
            .where(AgentPlanAction.approval_status == "approved")
        )
        actions = (await session.execute(actions_q)).scalars().all()

        succeeded = 0
        failed = 0
        manual_required = 0

        for action in actions:
            try:
                result = await _execute_action(session, run, action)
                action.execution_status = result.get("status", "success")
                action.execution_result = result
                if action.execution_status == "success":
                    succeeded += 1
                elif action.execution_status == "manual_required":
                    manual_required += 1
                else:
                    failed += 1
            except Exception as e:
                action.execution_status = "failed"
                action.error_message = str(e)
                action.execution_result = {"error": str(e)}
                failed += 1

        report = {
            "total": len(actions),
            "succeeded": succeeded,
            "failed": failed,
            "manual_required": manual_required,
        }
        run.execution_report = report
        run.status = "completed_with_errors" if (failed > 0 or manual_required > 0) else "completed"
        run.completed_at = datetime.now(timezone.utc)

    return {"run_id": run_id, "status": run.status, "report": report}


@app.post("/api/v1/agents/runs/{run_id}/cancel")
async def cancel_agent_plan(
    run_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Reject/cancel a plan. Transitions to 'cancelled'."""
    from datetime import datetime, timezone

    async with get_tenant_session(current_user.tenant_id) as session:
        run = await session.get(AgentRun, uuid.UUID(run_id))
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.status not in ("plan_ready", "approved"):
            raise HTTPException(status_code=409, detail=f"Run is in '{run.status}' state, cannot cancel")

        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)

    return {"run_id": run_id, "status": "cancelled"}


@app.get("/api/v1/agents/runs/{run_id}/report")
async def get_execution_report(
    run_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Fetch the execution report: run metadata + all action outcomes."""
    async with get_tenant_session(current_user.tenant_id) as session:
        run = await session.get(AgentRun, uuid.UUID(run_id))
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        actions_q = select(AgentPlanAction).where(AgentPlanAction.run_id == uuid.UUID(run_id))
        rows = (await session.execute(actions_q)).scalars().all()

        succeeded = [_row_to_dict(a) for a in rows if a.execution_status == "success"]
        failed = [_row_to_dict(a) for a in rows if a.execution_status == "failed"]
        manual = [_row_to_dict(a) for a in rows if a.execution_status == "manual_required"]
        skipped = [_row_to_dict(a) for a in rows if a.approval_status == "skipped"]

        return {
            "run": _row_to_dict(run),
            "report": run.execution_report,
            "succeeded": succeeded,
            "failed": failed,
            "manual_required": manual,
            "skipped": skipped,
        }


# ── Plan-phase helpers (per agent type) ──────────────────────

async def _plan_vms_match(
    session: Any,
    tenant_id: str,
    weeks_back: int,
    upload_id: str | None,
) -> tuple[list[dict], dict, Any]:
    """Run the VMS matching graph in plan mode and return structured plan actions."""
    from datetime import datetime, timedelta, timezone
    from src.agents.vms_matching.graph import get_graph

    vms_q = select(VMSRecord).where(VMSRecord.tenant_id == uuid.UUID(tenant_id))
    if upload_id:
        vms_q = vms_q.where(VMSRecord.upload_id == uuid.UUID(upload_id))
    else:
        cutoff = datetime.now(timezone.utc).date() - timedelta(weeks=weeks_back)
        vms_q = vms_q.where(VMSRecord.week_ending >= cutoff)
    vms_rows = (await session.execute(vms_q)).scalars().all()

    if not vms_rows:
        return [], {"agent_summary": "No VMS records found for the selected time period. Upload VMS data or adjust the lookback window to get started.", "records_analyzed": 0, "actions_proposed": 0}, None

    placement_rows = (await session.execute(select(Placement))).scalars().all()
    alias_rows = (await session.execute(
        select(VMSNameAlias).where(VMSNameAlias.tenant_id == uuid.UUID(tenant_id))
    )).scalars().all()
    aliases = {" ".join(a.vms_name.lower().split()): _row_to_dict(a) for a in alias_rows}

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

    graph = get_graph()
    graph_input = {
        "tenant_id": tenant_id,
        "vms_records": vms_records,
        "placements": placements,
        "aliases": aliases,
    }
    import asyncio as _asyncio
    result = await _asyncio.to_thread(graph.invoke, graph_input)

    matches = result.get("matches") or []
    plan_actions = []

    for m in matches:
        confidence = float(m.get("confidence") or 0)
        rate_delta = m.get("rate_delta")
        reg_hours = float(m.get("regular_hours") or 0)
        ot_hours = float(m.get("ot_hours") or 0)
        financial_impact = round(abs(float(rate_delta or 0)) * (reg_hours + ot_hours), 2)

        if m.get("match_method") == "unmatched":
            action_type = "investigate_unmatched"
            description = f"Investigate missing placement for {m.get('candidate_name', 'Unknown')}"
            severity = "high"
        elif abs(float(rate_delta or 0)) > 5:
            action_type = "flag_rate_discrepancy"
            description = f"Flag rate discrepancy for {m.get('candidate_name', 'Unknown')} — Δ${abs(float(rate_delta or 0)):.2f}/h"
            severity = "high" if financial_impact > 500 else "medium"
        elif confidence >= 0.95:
            action_type = "auto_approve_match"
            description = f"Auto-approve match for {m.get('candidate_name', 'Unknown')} ({m.get('match_method')}, {confidence:.0%} confidence)"
            severity = "low"
        elif confidence >= 0.70:
            action_type = "review_approve_match"
            description = f"Review and approve match for {m.get('candidate_name', 'Unknown')} ({m.get('match_method')}, {confidence:.0%} confidence)"
            severity = "medium"
        else:
            action_type = "flag_low_confidence"
            description = f"Flag low-confidence match for {m.get('candidate_name', 'Unknown')} ({confidence:.0%})"
            severity = "high"

        plan_actions.append({
            "action_type": action_type,
            "target_ref": str(m.get("id", "")),
            "target_name": m.get("candidate_name"),
            "description": description,
            "confidence": confidence,
            "severity": severity,
            "financial_impact": financial_impact,
            "details": {
                "match_method": m.get("match_method"),
                "matched_placement_id": m.get("matched_placement_id"),
                "matched_bullhorn_id": m.get("matched_bullhorn_id"),
                "name_similarity": m.get("name_similarity"),
                "rate_delta": rate_delta,
                "hours_delta": m.get("hours_delta"),
                "explanation": m.get("explanation"),
                "week_ending": m.get("week_ending"),
                "regular_hours": reg_hours,
                "ot_hours": ot_hours,
                "bill_rate": m.get("bill_rate"),
                "vms_platform": m.get("vms_platform"),
                "placement_ref": m.get("placement_ref"),
            },
        })

    graph_result = result.get("result") or {}
    plan_summary = {
        "records_analyzed": len(vms_records),
        "placements_loaded": len(placements),
        "actions_proposed": len(plan_actions),
        **graph_result,
    }

    return plan_actions, plan_summary, result.get("token_usage")


async def _plan_generic_agent(
    session: Any,
    tenant_id: str,
    graph_module: str,
    graph_input: dict[str, Any],
    output_key: str,
    action_mapper: Any,
) -> tuple[list[dict], dict, Any]:
    """Generic helper to run any analyze-only LangGraph agent and convert output to plan actions."""
    import importlib, asyncio as _asyncio
    mod = importlib.import_module(graph_module)
    graph = mod.get_graph()
    result = await _asyncio.to_thread(graph.invoke, graph_input)

    items = result.get(output_key) or []
    raw_result = result.get("result") or {}
    plan_actions = [action_mapper(item) for item in items]

    summary = {
        "agent_summary": raw_result.get("summary", "Analysis complete"),
        "actions_proposed": len(plan_actions),
        **{k: v for k, v in raw_result.items() if k != "summary"},
    }
    return plan_actions, summary, result.get("token_usage")


async def _plan_time_anomaly(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc).date() - timedelta(weeks=52)
    ts_q = select(Timesheet).where(
        Timesheet.tenant_id == uuid.UUID(tenant_id),
        Timesheet.week_ending >= cutoff,
    ).limit(500)
    rows = (await session.execute(ts_q)).scalars().all()
    if not rows:
        return [], {"agent_summary": "No timesheet records found. Sync timesheet data from Bullhorn to enable anomaly detection.", "records_analyzed": 0, "actions_proposed": 0}, None

    entries = [_row_to_dict(r) for r in rows]

    def map_anomaly(item: dict) -> dict:
        severity_map = {"high": "high", "medium": "medium", "low": "low"}
        return {
            "action_type": f"flag_{item.get('type', 'anomaly')}",
            "target_ref": str(item.get("entry_id", "")),
            "target_name": item.get("candidate_name"),
            "description": item.get("description", "Time anomaly detected"),
            "confidence": None,
            "severity": severity_map.get(item.get("severity", "medium"), "medium"),
            "financial_impact": None,
            "details": item,
        }

    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.time_anomaly.graph",
        {"tenant_id": tenant_id, "time_entries": entries},
        "anomalies",
        map_anomaly,
    )


async def _plan_invoice_matching(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    inv_q = select(Invoice).where(Invoice.tenant_id == uuid.UUID(tenant_id))
    inv_rows = (await session.execute(inv_q)).scalars().all()
    if not inv_rows:
        return [], {"agent_summary": "No invoice records found. Sync invoice data from Bullhorn to enable invoice matching.", "records_analyzed": 0, "actions_proposed": 0}, None
    invoices = [_row_to_dict(r) for r in inv_rows]

    def map_match(item: dict) -> dict:
        conf = float(item.get("confidence", 0))
        discreps = item.get("discrepancies", [])
        if discreps:
            return {
                "action_type": "flag_invoice_discrepancy",
                "target_ref": item.get("invoice_id", ""),
                "target_name": item.get("po_id"),
                "description": f"Invoice {item.get('invoice_id')} has {len(discreps)} discrepancy(ies) against PO {item.get('po_id')}",
                "confidence": conf,
                "severity": "high" if conf < 0.80 else "medium",
                "financial_impact": None,
                "details": item,
            }
        return {
            "action_type": "approve_invoice_match",
            "target_ref": item.get("invoice_id", ""),
            "target_name": item.get("po_id"),
            "description": f"Match invoice {item.get('invoice_id')} to PO {item.get('po_id')} ({conf:.0%} confidence)",
            "confidence": conf,
            "severity": "low" if conf >= 0.95 else "medium",
            "financial_impact": None,
            "details": item,
        }

    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.invoice_matching.graph",
        {"tenant_id": tenant_id, "invoices": invoices, "purchase_orders": []},
        "proposed_matches",
        map_match,
    )


async def _plan_collections(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    inv_q = select(Invoice).where(
        Invoice.tenant_id == uuid.UUID(tenant_id),
        Invoice.days_outstanding > 0,
    )
    inv_rows = (await session.execute(inv_q)).scalars().all()
    if not inv_rows:
        return [], {"agent_summary": "No outstanding invoices found. All invoices are current — nothing to collect.", "records_analyzed": 0, "actions_proposed": 0}, None

    ar_aging = [
        {
            "client_id": r.client_name,
            "client_name": r.client_name,
            "amount": float(r.amount) if r.amount else 0,
            "days_past_due": r.days_outstanding or 0,
            "invoice_number": r.invoice_number,
        }
        for r in inv_rows
    ]

    def map_action(item: dict) -> dict:
        action_type = item.get("action_type", "send_reminder")
        days = item.get("days_past_due", 0)
        severity = "high" if days > 90 else "medium" if days > 60 else "low"
        return {
            "action_type": action_type,
            "target_ref": item.get("client_id", ""),
            "target_name": item.get("client_name"),
            "description": item.get("next_step", f"{action_type} for {item.get('client_name', 'Unknown')}"),
            "confidence": None,
            "severity": severity,
            "financial_impact": item.get("amount"),
            "details": item,
        }

    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.collections.graph",
        {"tenant_id": tenant_id, "ar_aging": ar_aging},
        "suggested_actions",
        map_action,
    )


async def _plan_compliance(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    activity_q = select(AuditLog).where(
        AuditLog.tenant_id == uuid.UUID(tenant_id),
        AuditLog.created_at >= cutoff,
    ).limit(200)
    activity_rows = (await session.execute(activity_q)).scalars().all()
    if not activity_rows:
        return [], {"agent_summary": "No audit activity found in the last 90 days. As operations are logged, the compliance agent will monitor for policy violations.", "records_analyzed": 0, "actions_proposed": 0}, None
    activity = [_row_to_dict(r) for r in activity_rows]

    def map_violation(item: dict) -> dict:
        return {
            "action_type": f"flag_{item.get('severity', 'medium')}_violation",
            "target_ref": item.get("activity_id", ""),
            "target_name": item.get("policy_id"),
            "description": item.get("description", "Compliance violation detected"),
            "confidence": None,
            "severity": item.get("severity", "medium"),
            "financial_impact": None,
            "details": item,
        }

    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.compliance.graph",
        {"tenant_id": tenant_id, "activity_log": activity, "policies": []},
        "violations",
        map_violation,
    )


async def _plan_risk_alert(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    """Risk alert uses placement data to identify rate/hours/compliance risks."""
    placement_rows = (await session.execute(
        select(Placement).where(Placement.tenant_id == uuid.UUID(tenant_id))
    )).scalars().all()
    if not placement_rows:
        return [], {"agent_summary": "No placement records found. Sync placement data from Bullhorn to enable risk monitoring.", "records_analyzed": 0, "actions_proposed": 0}, None

    placements = [_row_to_dict(p) for p in placement_rows]

    def map_risk(item: dict) -> dict:
        return {
            "action_type": f"flag_{item.get('risk_type', 'risk')}",
            "target_ref": str(item.get("placement_id", "")),
            "target_name": item.get("candidate_name"),
            "description": item.get("description", "Risk detected"),
            "confidence": None,
            "severity": item.get("severity", "medium"),
            "financial_impact": item.get("financial_impact"),
            "details": item,
        }

    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.risk_alert.graph",
        {"tenant_id": tenant_id, "placements": placements},
        "risks",
        map_risk,
    )


async def _plan_gl_reconciliation(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    # In production, this would fetch from a GL integration (QuickBooks/Xero)
    # For now we use placeholder logic or mocked data if available
    def map_gl(item: dict) -> dict:
        return {
            "action_type": f"flag_{item.get('discrepancy_type', 'gl_discrepancy')}",
            "target_ref": item.get("gl_entry_id", ""),
            "target_name": f"GL Entry {item.get('gl_entry_id')}",
            "description": item.get("description", "GL Discrepancy detected"),
            "confidence": None,
            "severity": item.get("severity", "medium"),
            "financial_impact": item.get("financial_impact"),
            "details": item,
        }
    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.gl_reconciliation.graph",
        {"tenant_id": tenant_id, "gl_entries": [], "charges": []},
        "discrepancies",
        map_gl,
    )


async def _plan_payroll_reconciliation(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    def map_payroll(item: dict) -> dict:
        return {
            "action_type": f"flag_{item.get('discrepancy_type', 'payroll_discrepancy')}",
            "target_ref": item.get("payroll_id", ""),
            "target_name": item.get("candidate_name"),
            "description": item.get("description", "Payroll Discrepancy detected"),
            "confidence": None,
            "severity": item.get("severity", "medium"),
            "financial_impact": item.get("financial_impact"),
            "details": item,
        }
    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.payroll_reconciliation.graph",
        {"tenant_id": tenant_id, "payroll_records": [], "charges": []},
        "discrepancies",
        map_payroll,
    )


async def _plan_forecasting(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    def map_forecast(item: dict) -> dict:
        return {
            "action_type": "report_forecast",
            "target_ref": "forecast",
            "target_name": "Revenue Forecast",
            "description": "Financial forecast generated",
            "confidence": None,
            "severity": "info",
            "financial_impact": None,
            "details": item,
        }
    # Forecasting returns a dict, not a list of actions usually, so we wrap it
    pa, summary, tokens = await _plan_generic_agent(
        session, tenant_id,
        "src.agents.forecasting.graph",
        {"tenant_id": tenant_id, "billing_history": [], "payroll_history": []},
        "forecast",
        map_forecast,
    )
    return pa, summary, tokens


async def _plan_kpi(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    def map_kpi(item: dict) -> dict:
        return {
            "action_type": f"flag_kpi_{item.get('metric')}",
            "target_ref": item.get("metric", ""),
            "target_name": item.get("metric"),
            "description": f"KPI {item.get('metric')} alert: {item.get('status')}",
            "confidence": None,
            "severity": "medium",
            "financial_impact": None,
            "details": item,
        }
    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.kpi.graph",
        {"tenant_id": tenant_id, "metrics_data": {}},
        "alerts",
        map_kpi,
    )


async def _plan_commissions(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    def map_comm(item: dict) -> dict:
        return {
            "action_type": "calculate_commission",
            "target_ref": item.get("placement_id", ""),
            "target_name": item.get("candidate_name"),
            "description": f"Calculate commissions for {item.get('candidate_name')}",
            "confidence": None,
            "severity": "info",
            "financial_impact": sum(c["amount"] for c in item.get("commissions", [])),
            "details": item,
        }
    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.commissions.graph",
        {"tenant_id": tenant_id, "placements": []},
        "commissions",
        map_comm,
    )


async def _plan_contract_compliance(session: Any, tenant_id: str) -> tuple[list[dict], dict, Any]:
    def map_violation(item: dict) -> dict:
        return {
            "action_type": f"flag_{item.get('violation_type')}",
            "target_ref": item.get("placement_id", ""),
            "target_name": item.get("candidate_name"),
            "description": item.get("description", "Contract violation detected"),
            "confidence": None,
            "severity": item.get("severity", "medium"),
            "financial_impact": None,
            "details": item,
        }
    return await _plan_generic_agent(
        session, tenant_id,
        "src.agents.contract_compliance.graph",
        {"tenant_id": tenant_id, "placements": [], "contracts": []},
        "violations",
        map_violation,
    )


async def _execute_action(session: Any, run: AgentRun, action: AgentPlanAction) -> dict:
    """Execute a single plan action. Currently records intent; Bullhorn write-back is a future integration."""
    agent_type = run.agent_type

    if agent_type == "vms-match":
        details = action.details or {}
        confidence = float(action.confidence or 0)
        if action.action_type in ("auto_approve_match", "review_approve_match"):
            match = VMSMatch(
                tenant_id=run.tenant_id,
                run_id=run.id,
                vms_record_id=uuid.UUID(action.target_ref) if action.target_ref else None,
                placement_id=uuid.UUID(details["matched_placement_id"]) if details.get("matched_placement_id") else None,
                bullhorn_id=details.get("matched_bullhorn_id"),
                confidence=confidence,
                match_method=details.get("match_method"),
                name_similarity=details.get("name_similarity"),
                rate_delta=details.get("rate_delta"),
                hours_delta=details.get("hours_delta"),
                financial_impact=action.financial_impact,
                llm_explanation=details.get("explanation"),
                status="approved" if confidence >= 0.95 else "pending",
            )
            session.add(match)
            return {"status": "success", "message": f"Match created for {action.target_name}"}
        elif action.action_type in ("flag_rate_discrepancy", "flag_low_confidence", "investigate_unmatched"):
            return {"status": "manual_required", "message": f"Flagged for manual review: {action.description}"}

    # For all other agent types, record the action as executed
    return {"status": "success", "message": f"Action recorded: {action.description}"}


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
