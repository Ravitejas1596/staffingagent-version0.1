"""Application configuration loaded from environment variables.

Security Sprint (Workstream 5) hardening:
- jwt_secret has no default — FastAPI refuses to boot if it is missing or
  shorter than 32 characters. This prevents the classic "change-me-in-production"
  default from ever reaching a deployed container.
- Access-token TTL is 60 minutes. Silent refresh via /api/v1/auth/refresh
  keeps the user logged in for as long as they are active without ever
  holding a long-lived token on the client.
"""
from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


_DEV_JWT_SECRET_SENTINELS = {
    "",
    "change-me-in-production",
    "changeme",
    "secret",
    "your-secret-here",
    "replace-me",
}


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://app_user:changeme_in_production@localhost:5432/staffingagent"
    database_admin_url: str = "postgresql+asyncpg://postgres:localdev@localhost:5432/staffingagent"

    # Required. No default — see module docstring.
    jwt_secret: str = Field(..., description="JWT HMAC signing key; min 32 chars")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    jwt_refresh_window_minutes: int = 60 * 24 * 7  # 7 days: max age after last refresh

    s3_bucket: str = "staffingagent-uploads"
    aws_endpoint_url: str = ""
    aws_default_region: str = "us-east-1"

    anthropic_api_key: str = ""

    github_token: str = ""
    github_repo: str = "StaffingAgent-ai/StaffingAgent"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://app.staffingagent.ai",
        "https://staffingagent.ai",
        "https://www.staffingagent.ai",
        "https://d393bn18pj5hcl.cloudfront.net",
    ]

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if v in _DEV_JWT_SECRET_SENTINELS:
            raise ValueError(
                "JWT_SECRET is unset or still at its development default. "
                "Set JWT_SECRET to a randomly-generated value (openssl rand -base64 48)."
            )
        if len(v) < 32:
            raise ValueError(
                f"JWT_SECRET must be at least 32 characters (got {len(v)}). "
                "Generate a new one with: openssl rand -base64 48"
            )
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
