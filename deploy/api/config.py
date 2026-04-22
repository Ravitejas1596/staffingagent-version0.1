"""Application configuration loaded from environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://app_user:changeme_in_production@localhost:5432/staffingagent"
    database_admin_url: str = "postgresql+asyncpg://postgres:localdev@localhost:5432/staffingagent"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours

    s3_bucket: str = "staffingagent-uploads"
    aws_endpoint_url: str = ""  # set for LocalStack, empty for real AWS
    aws_default_region: str = "us-east-1"

    anthropic_api_key: str = ""

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://app.staffingagent.ai",
        "https://staffingagent.ai",
        "https://www.staffingagent.ai",
        "https://d393bn18pj5hcl.cloudfront.net",
    ]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
