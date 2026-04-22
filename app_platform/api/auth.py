"""JWT authentication for the StaffingAgent API.

Pilot: email + password login → JWT with tenant_id + user_id + role.
Future: Bullhorn OAuth SSO integration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app_platform.api.config import settings

bearer_scheme = HTTPBearer()


class TokenPayload(BaseModel):
    sub: str          # user_id
    tenant_id: str
    role: str
    exp: Optional[datetime] = None


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, tenant_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**data)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenPayload:
    """FastAPI dependency: extract and validate the JWT from the Authorization header."""
    return decode_token(credentials.credentials)


async def require_role(minimum: str, current: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Check that the user has at least the specified role level."""
    hierarchy = {"viewer": 0, "manager": 1, "admin": 2, "super_admin": 3}
    if hierarchy.get(current.role, 0) < hierarchy.get(minimum, 99):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current


async def require_admin(current: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    return await require_role("admin", current)


async def require_super_admin(current: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    return await require_role("super_admin", current)
