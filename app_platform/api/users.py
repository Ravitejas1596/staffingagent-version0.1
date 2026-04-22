"""User management endpoints — admin-only CRUD, invitations, and permission updates.

Mounted at /api/v1/users on the main app.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app_platform.api.auth import TokenPayload, get_current_user, hash_password, require_admin, require_role
from app_platform.api.database import get_tenant_session
from app_platform.api.models import User

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# ── Default permission matrices per role ─────────────────────

ROLE_DEFAULT_PERMISSIONS: dict[str, dict[str, dict[str, bool]]] = {
    "super_admin": {
        "dashboard": {"view": True},
        "timeops": {"view": True, "execute": True},
        "riskops": {"view": True, "resolve": True, "execute": True},
        "agents": {"view": True, "trigger": True, "approve": True},
        "settings": {"view": True, "edit": True},
        "users": {"view": True, "manage": True},
    },
    "admin": {
        "dashboard": {"view": True},
        "timeops": {"view": True, "execute": True},
        "riskops": {"view": True, "resolve": True, "execute": True},
        "agents": {"view": True, "trigger": True, "approve": True},
        "settings": {"view": True, "edit": True},
        "users": {"view": True, "manage": True},
    },
    "manager": {
        "dashboard": {"view": True},
        "timeops": {"view": True, "execute": True},
        "riskops": {"view": True, "resolve": True, "execute": True},
        "agents": {"view": True, "trigger": True, "approve": True},
        "settings": {"view": False, "edit": False},
        "users": {"view": False, "manage": False},
    },
    "viewer": {
        "dashboard": {"view": True},
        "timeops": {"view": True, "execute": False},
        "riskops": {"view": True, "resolve": False, "execute": False},
        "agents": {"view": True, "trigger": False, "approve": False},
        "settings": {"view": False, "edit": False},
        "users": {"view": False, "manage": False},
    },
}

VALID_ROLES = list(ROLE_DEFAULT_PERMISSIONS.keys())


# Role hierarchy levels. Must match require_role() in auth.py.
ROLE_HIERARCHY = {"viewer": 0, "manager": 1, "admin": 2, "super_admin": 3}


def assert_can_assign_role(
    *,
    caller_role: str,
    target_role: str,
    caller_sub: str,
    target_user_id: str | None = None,
    via_endpoint: str = "",
) -> None:
    """Refuse privilege-escalation attempts on role assignment.

    Rules enforced (Security Sprint Workstream 6):
      1. `super_admin` cannot be granted via any API endpoint. Only the
         platform bootstrap SQL can mint a super_admin.
      2. A caller cannot assign a role strictly higher than their own.
         (admins can manage admins; managers cannot create admins.)
      3. A caller cannot change their own role.

    Args are kwargs-only so the call site is self-documenting. We avoid a
    `caller: TokenPayload` parameter to keep this helper testable without
    needing to construct a JWT payload.
    """
    if target_role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role. Must be one of: {VALID_ROLES}",
        )

    if target_role == "super_admin":
        raise HTTPException(
            status_code=403,
            detail="The super_admin role cannot be granted via the API; use the platform bootstrap.",
        )

    caller_level = ROLE_HIERARCHY.get(caller_role, -1)
    target_level = ROLE_HIERARCHY.get(target_role, 99)
    if target_level > caller_level:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot assign role '{target_role}': requires caller to be at least '{target_role}'",
        )

    if target_user_id and target_user_id == caller_sub:
        raise HTTPException(
            status_code=403,
            detail="You cannot change your own role.",
        )


async def record_role_change(
    session: Any,
    *,
    tenant_id: str,
    target_user_id: str,
    caller_user_id: str,
    from_role: str | None,
    to_role: str,
    via_endpoint: str,
) -> None:
    """Append a row to role_change_audit. Called on every successful role set."""
    # Local import avoids a circular import between users.py and models.py
    # while keeping the helper self-contained.
    from app_platform.api.models import RoleChangeAudit

    entry = RoleChangeAudit(
        tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
        target_user_id=uuid.UUID(target_user_id),
        caller_user_id=uuid.UUID(caller_user_id),
        from_role=from_role,
        to_role=to_role,
        via_endpoint=via_endpoint,
    )
    session.add(entry)


def effective_permissions(role: str, overrides: dict[str, Any] | None) -> dict[str, dict[str, bool]]:
    """Merge role defaults with any per-user overrides."""
    base = {
        area: {perm: val for perm, val in perms.items()}
        for area, perms in ROLE_DEFAULT_PERMISSIONS.get(role, ROLE_DEFAULT_PERMISSIONS["viewer"]).items()
    }
    if overrides:
        for area, perms in overrides.items():
            if area in base and isinstance(perms, dict):
                for perm, val in perms.items():
                    if perm in base[area] and isinstance(val, bool):
                        base[area][perm] = val
    return base


# ── Request / response schemas ───────────────────────────────

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    permissions: dict[str, dict[str, bool]]
    is_active: bool
    invited_by: Optional[str] = None
    invited_by_name: Optional[str] = None
    invited_at: Optional[str] = None
    last_login_at: Optional[str] = None
    created_at: str


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    role: str = "viewer"
    password: Optional[str] = None
    permissions: Optional[dict[str, dict[str, bool]]] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    permissions: Optional[dict[str, dict[str, bool]]] = None


class InviteRequest(BaseModel):
    email: EmailStr
    name: str
    role: str = "viewer"
    password: Optional[str] = None
    permissions: Optional[dict[str, dict[str, bool]]] = None


class SetPasswordRequest(BaseModel):
    password: str


class UserListResponse(BaseModel):
    users: list[UserOut]
    total: int


class PermissionsReference(BaseModel):
    roles: list[str]
    defaults: dict[str, dict[str, dict[str, bool]]]


# ── Helpers ──────────────────────────────────────────────────

def _ts(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def _user_to_out(user: User, session: Any) -> UserOut:
    """Convert ORM User to API response, resolving invited_by name."""
    inviter_name: str | None = None
    if user.invited_by:
        row = await session.execute(select(User.name).where(User.id == user.invited_by))
        inviter_name = row.scalar_one_or_none()

    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        permissions=effective_permissions(user.role, user.permissions),
        is_active=user.is_active,
        invited_by=str(user.invited_by) if user.invited_by else None,
        invited_by_name=inviter_name,
        invited_at=_ts(user.invited_at),
        last_login_at=_ts(user.last_login_at),
        created_at=_ts(user.created_at),
    )


# ── Endpoints ────────────────────────────────────────────────

@router.get("/permissions-reference", response_model=PermissionsReference)
async def get_permissions_reference(
    admin: TokenPayload = Depends(require_admin),
):
    """Return the default permission matrix for all roles (UI reference)."""
    return PermissionsReference(roles=VALID_ROLES, defaults=ROLE_DEFAULT_PERMISSIONS)


@router.get("", response_model=UserListResponse)
async def list_users(
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    admin: TokenPayload = Depends(require_admin),
):
    """List all users in the tenant. Admin only."""
    async with get_tenant_session(admin.tenant_id) as session:
        q = select(User).order_by(User.created_at.desc())
        if role:
            q = q.where(User.role == role)
        if is_active is not None:
            q = q.where(User.is_active == is_active)
        if search:
            pattern = f"%{search}%"
            q = q.where((User.name.ilike(pattern)) | (User.email.ilike(pattern)))

        total = await session.scalar(select(func.count()).select_from(q.subquery()))
        rows = await session.execute(q.limit(limit).offset(offset))
        users = rows.scalars().all()
        out = [await _user_to_out(u, session) for u in users]
        return UserListResponse(users=out, total=total or 0)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    admin: TokenPayload = Depends(require_admin),
):
    """Get a single user by ID. Admin only."""
    async with get_tenant_session(admin.tenant_id) as session:
        row = await session.execute(select(User).where(User.id == user_id))
        user = row.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return await _user_to_out(user, session)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    admin: TokenPayload = Depends(require_admin),
):
    """Create a new user. Admin only."""
    assert_can_assign_role(
        caller_role=admin.role,
        target_role=body.role,
        caller_sub=admin.sub,
        via_endpoint="POST /api/v1/users",
    )

    async with get_tenant_session(admin.tenant_id) as session:
        existing = await session.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A user with this email already exists")

        user = User(
            tenant_id=uuid.UUID(admin.tenant_id),
            email=body.email,
            name=body.name,
            role=body.role,
            password_hash=hash_password(body.password) if body.password else None,
            permissions=body.permissions or {},
            invited_by=uuid.UUID(admin.sub),
            invited_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.flush()
        await record_role_change(
            session,
            tenant_id=admin.tenant_id,
            target_user_id=str(user.id),
            caller_user_id=admin.sub,
            from_role=None,
            to_role=body.role,
            via_endpoint="POST /api/v1/users",
        )
        return await _user_to_out(user, session)


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    admin: TokenPayload = Depends(require_admin),
):
    """Update user fields. Admin only."""
    async with get_tenant_session(admin.tenant_id) as session:
        row = await session.execute(select(User).where(User.id == user_id))
        user = row.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if body.email is not None:
            existing = await session.execute(select(User).where(User.email == body.email, User.id != user.id))
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Another user already has this email")
            user.email = body.email
        if body.name is not None:
            user.name = body.name
        previous_role = user.role
        if body.role is not None and body.role != previous_role:
            # Block super_admin self-promotion and cross-level escalation.
            # Caller must have at least the target role, and nobody can
            # grant super_admin through this endpoint.
            assert_can_assign_role(
                caller_role=admin.role,
                target_role=body.role,
                caller_sub=admin.sub,
                target_user_id=user_id,
                via_endpoint="PUT /api/v1/users/{id}",
            )
            # Also block demoting the last super_admin (future hardening) —
            # for now just block editing a super_admin's role via the API.
            if previous_role == "super_admin":
                raise HTTPException(
                    status_code=403,
                    detail="The role of a super_admin cannot be changed via the API.",
                )
            user.role = body.role
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.permissions is not None:
            user.permissions = body.permissions

        await session.flush()
        if body.role is not None and body.role != previous_role:
            await record_role_change(
                session,
                tenant_id=admin.tenant_id,
                target_user_id=user_id,
                caller_user_id=admin.sub,
                from_role=previous_role,
                to_role=body.role,
                via_endpoint="PUT /api/v1/users/{id}",
            )
        return await _user_to_out(user, session)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    admin: TokenPayload = Depends(require_admin),
):
    """Soft-delete: deactivates a user rather than removing the record."""
    if user_id == admin.sub:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    async with get_tenant_session(admin.tenant_id) as session:
        row = await session.execute(select(User).where(User.id == user_id))
        user = row.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_active = False


async def _require_manager(current: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    return await require_role("manager", current)


@router.post("/invite", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: InviteRequest,
    caller: TokenPayload = Depends(_require_manager),
):
    """Create a user and send an invitation. Manager+ can invite.

    Role-assignment rules are enforced by assert_can_assign_role: the
    caller cannot invite a role higher than their own, and super_admin
    is never assignable via the API.
    """
    assert_can_assign_role(
        caller_role=caller.role,
        target_role=body.role,
        caller_sub=caller.sub,
        via_endpoint="POST /api/v1/users/invite",
    )

    async with get_tenant_session(caller.tenant_id) as session:
        existing = await session.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A user with this email already exists")

        user = User(
            tenant_id=uuid.UUID(caller.tenant_id),
            email=body.email,
            name=body.name,
            role=body.role,
            password_hash=hash_password(body.password) if body.password else None,
            permissions=body.permissions or {},
            invited_by=uuid.UUID(caller.sub),
            invited_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.flush()
        await record_role_change(
            session,
            tenant_id=caller.tenant_id,
            target_user_id=str(user.id),
            caller_user_id=caller.sub,
            from_role=None,
            to_role=body.role,
            via_endpoint="POST /api/v1/users/invite",
        )
        return await _user_to_out(user, session)


@router.post("/{user_id}/invite", response_model=UserOut)
async def resend_invite(
    user_id: str,
    admin: TokenPayload = Depends(require_admin),
):
    """Mark a user as re-invited (updates invited_at timestamp)."""
    async with get_tenant_session(admin.tenant_id) as session:
        row = await session.execute(select(User).where(User.id == user_id))
        user = row.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.invited_at = datetime.now(timezone.utc)
        user.invited_by = uuid.UUID(admin.sub)
        await session.flush()
        return await _user_to_out(user, session)


@router.post("/{user_id}/set-password", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_password(
    user_id: str,
    body: SetPasswordRequest,
    admin: TokenPayload = Depends(require_admin),
):
    """Set or reset a user's password. Admin only."""
    async with get_tenant_session(admin.tenant_id) as session:
        row = await session.execute(select(User).where(User.id == user_id))
        user = row.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.password_hash = hash_password(body.password)
