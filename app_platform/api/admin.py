"""Platform admin endpoints — super_admin-only tenant and cross-tenant user management.

Mounted at /api/v1/admin on the main app.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app_platform.api.auth import TokenPayload, hash_password, require_super_admin
from app_platform.api.crypto import (
    CryptoError,
    current_key_version,
    decrypt_credentials,
    encrypt_credentials,
)
from app_platform.api.database import get_platform_session, get_tenant_session
from app_platform.api.models import Tenant, User
from app_platform.api.users import (
    VALID_ROLES,
    _user_to_out,
    assert_can_assign_role,
    effective_permissions,
    record_role_change,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ── Request / response schemas ───────────────────────────────

class TenantCreate(BaseModel):
    name: str
    slug: str
    tier: str = "assess"


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    tier: str
    is_active: bool
    created_at: str
    has_bullhorn_config: bool
    user_count: int = 0


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    tier: Optional[str] = None
    is_active: Optional[bool] = None


class BullhornCredentials(BaseModel):
    client_id: str
    client_secret: str
    api_user: str
    api_password: str


class TenantUserCreate(BaseModel):
    email: EmailStr
    name: str
    role: str = "admin"
    password: str


# ── Helpers ──────────────────────────────────────────────────

VALID_TIERS = ("assess", "transform", "enterprise")


def _ts(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _tenant_out(tenant: Tenant, user_count: int = 0) -> TenantOut:
    # has_bullhorn_config is true once credentials have been written to the
    # encrypted column. The legacy plaintext fallback lets us report correctly
    # on rows that have not yet been migrated by the one-shot re-encryption
    # script; it will disappear once scripts/encrypt_existing_bullhorn_creds.py
    # runs in production.
    has_bh = bool(tenant.bullhorn_credentials_ciphertext) or bool(
        tenant.bullhorn_config and tenant.bullhorn_config.get("client_id")
    )
    return TenantOut(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        tier=tenant.tier or "assess",
        is_active=tenant.is_active,
        created_at=_ts(tenant.created_at),
        has_bullhorn_config=has_bh,
        user_count=user_count,
    )


# ── Tenant endpoints ─────────────────────────────────────────

@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(
    _: TokenPayload = Depends(require_super_admin),
):
    """List all tenants with user counts."""
    async with get_platform_session() as session:
        user_counts_q = (
            select(User.tenant_id, func.count(User.id).label("cnt"))
            .group_by(User.tenant_id)
        )
        user_counts = {
            row.tenant_id: row.cnt
            for row in (await session.execute(user_counts_q)).all()
        }

        rows = await session.execute(
            select(Tenant).order_by(Tenant.created_at.desc())
        )
        tenants = rows.scalars().all()
        return [_tenant_out(t, user_counts.get(t.id, 0)) for t in tenants]


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    _: TokenPayload = Depends(require_super_admin),
):
    """Create a new tenant."""
    if body.tier not in VALID_TIERS:
        raise HTTPException(status_code=422, detail=f"Invalid tier. Must be one of: {VALID_TIERS}")

    slug = body.slug.lower().strip().replace(" ", "-")
    if not slug or not slug.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=422, detail="Slug must be URL-safe (letters, numbers, hyphens)")

    async with get_platform_session() as session:
        existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A tenant with this slug already exists")

        tenant = Tenant(
            name=body.name,
            slug=slug,
            tier=body.tier,
        )
        session.add(tenant)
        await session.flush()
        return _tenant_out(tenant)


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: str,
    _: TokenPayload = Depends(require_super_admin),
):
    """Fetch a single tenant."""
    async with get_platform_session() as session:
        row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = row.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        user_count = await session.scalar(
            select(func.count(User.id)).where(User.tenant_id == tenant.id)
        ) or 0
        return _tenant_out(tenant, user_count)


@router.put("/tenants/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    _: TokenPayload = Depends(require_super_admin),
):
    """Update tenant name, tier, or active status."""
    async with get_platform_session() as session:
        row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = row.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        if body.name is not None:
            tenant.name = body.name
        if body.tier is not None:
            if body.tier not in VALID_TIERS:
                raise HTTPException(status_code=422, detail=f"Invalid tier. Must be one of: {VALID_TIERS}")
            tenant.tier = body.tier
        if body.is_active is not None:
            tenant.is_active = body.is_active

        await session.flush()
        user_count = await session.scalar(
            select(func.count(User.id)).where(User.tenant_id == tenant.id)
        ) or 0
        return _tenant_out(tenant, user_count)


@router.put("/tenants/{tenant_id}/credentials")
async def update_credentials(
    tenant_id: str,
    body: BullhornCredentials,
    _: TokenPayload = Depends(require_super_admin),
):
    """Store Bullhorn API credentials encrypted at rest.

    Credentials are never returned by any endpoint after save. The ciphertext
    uses Fernet (see app_platform/api/crypto.py); the key is sourced from
    AWS Secrets Manager via the BULLHORN_CREDS_KEK env var.
    """
    async with get_platform_session() as session:
        row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = row.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        try:
            ciphertext = encrypt_credentials({
                "client_id": body.client_id,
                "client_secret": body.client_secret,
                "api_user": body.api_user,
                "api_password": body.api_password,
            })
        except CryptoError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Credential encryption unavailable: {exc}",
            )

        tenant.bullhorn_credentials_ciphertext = ciphertext
        tenant.bullhorn_credentials_version = current_key_version()
        tenant.bullhorn_credentials_updated_at = datetime.now(timezone.utc)

        # Wipe any plaintext that may have been stored before migration 042.
        if tenant.bullhorn_config:
            cleaned = {
                k: v for k, v in tenant.bullhorn_config.items()
                if k not in ("client_id", "client_secret", "api_user", "api_password")
            }
            cleaned["configured_at"] = datetime.now(timezone.utc).isoformat()
            tenant.bullhorn_config = cleaned
        else:
            tenant.bullhorn_config = {"configured_at": datetime.now(timezone.utc).isoformat()}

        await session.flush()
        return {"ok": True}


@router.post("/tenants/{tenant_id}/test-connection")
async def test_connection(
    tenant_id: str,
    _: TokenPayload = Depends(require_super_admin),
):
    """Validate stored Bullhorn credentials by attempting an auth token fetch."""
    async with get_platform_session() as session:
        row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = row.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Prefer the encrypted blob (written by migration 042+); fall back to
        # the legacy plaintext JSONB until every tenant has been migrated by
        # scripts/encrypt_existing_bullhorn_creds.py.
        creds: dict[str, Any] = {}
        if tenant.bullhorn_credentials_ciphertext:
            try:
                creds = decrypt_credentials(tenant.bullhorn_credentials_ciphertext)
            except CryptoError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Stored credentials could not be decrypted: {exc}",
                )
        else:
            legacy = tenant.bullhorn_config or {}
            creds = {
                "client_id": legacy.get("client_id"),
                "client_secret": legacy.get("client_secret"),
                "api_user": legacy.get("api_user"),
                "api_password": legacy.get("api_password"),
            }

        client_id = creds.get("client_id")
        client_secret = creds.get("client_secret")
        username = creds.get("api_user")
        password = creds.get("api_password")

        if not all([client_id, client_secret, username, password]):
            raise HTTPException(status_code=400, detail="Bullhorn credentials not configured")

        auth_base = "https://auth.bullhornstaffing.com"
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                auth_resp = await client.get(
                    f"{auth_base}/oauth/authorize",
                    params={
                        "client_id": client_id,
                        "response_type": "code",
                        "action": "Login",
                        "username": username,
                        "password": password,
                    },
                )
                if auth_resp.status_code >= 400:
                    return {"ok": False, "error": f"Auth returned {auth_resp.status_code}"}

                return {"ok": True, "message": "Bullhorn credentials are valid"}
        except httpx.TimeoutException:
            return {"ok": False, "error": "Connection timed out"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ── Cross-tenant user endpoints ──────────────────────────────

@router.get("/tenants/{tenant_id}/users")
async def list_tenant_users(
    tenant_id: str,
    _: TokenPayload = Depends(require_super_admin),
):
    """List all users in a specific tenant."""
    async with get_platform_session() as session:
        tenant_row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        if not tenant_row.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Tenant not found")

    async with get_tenant_session(tenant_id) as session:
        rows = await session.execute(
            select(User).where(User.tenant_id == tenant_id).order_by(User.created_at.desc())
        )
        users = rows.scalars().all()
        return [await _user_to_out(u, session) for u in users]


@router.post("/tenants/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
async def create_tenant_user(
    tenant_id: str,
    body: TenantUserCreate,
    caller: TokenPayload = Depends(require_super_admin),
):
    """Create a user in any tenant. tenant_id comes from URL, not JWT.

    Even super_admin cannot mint another super_admin via this endpoint —
    that requires the platform bootstrap SQL (Workstream 6 rule).
    """
    assert_can_assign_role(
        caller_role=caller.role,
        target_role=body.role,
        caller_sub=caller.sub,
        via_endpoint="POST /api/v1/admin/tenants/{id}/users",
    )

    async with get_platform_session() as session:
        tenant_row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        if not tenant_row.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Tenant not found")

    async with get_tenant_session(tenant_id) as session:
        existing = await session.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A user with this email already exists in this tenant")

        user = User(
            tenant_id=uuid.UUID(tenant_id),
            email=body.email,
            name=body.name,
            role=body.role,
            password_hash=hash_password(body.password),
            permissions={},
            invited_by=uuid.UUID(caller.sub),
            invited_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.flush()
        await record_role_change(
            session,
            tenant_id=tenant_id,
            target_user_id=str(user.id),
            caller_user_id=caller.sub,
            from_role=None,
            to_role=body.role,
            via_endpoint="POST /api/v1/admin/tenants/{id}/users",
        )
        return await _user_to_out(user, session)
