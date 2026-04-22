"""JWT authentication for the StaffingAgent API.

Pilot: email + password login → JWT with tenant_id + user_id + role.
Future: Bullhorn OAuth SSO integration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from platform.api.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


class TokenPayload(BaseModel):
    sub: str          # user_id
    tenant_id: str
    role: str
    exp: Optional[datetime] = None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


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


ROLE_HIERARCHY: dict[str, int] = {"viewer": 0, "manager": 1, "admin": 2}


async def require_role(minimum: str, current: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Check that the user has at least the specified role level."""
    if ROLE_HIERARCHY.get(current.role, 0) < ROLE_HIERARCHY.get(minimum, 99):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current


async def require_admin(current: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """FastAPI dependency: require admin role."""
    if current.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current


async def require_manager(current: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """FastAPI dependency: require at least manager role."""
    if ROLE_HIERARCHY.get(current.role, 0) < ROLE_HIERARCHY.get("manager", 1):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
    return current
