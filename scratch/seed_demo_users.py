import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from app_platform.api.database import engine, get_platform_session
from app_platform.api.models import Tenant, User
from app_platform.api.auth import hash_password

async def seed():
    async with get_platform_session() as session:
        # 1. Create or get Demo Tenant
        res = await session.execute(select(Tenant).where(Tenant.slug == "ghr-demo"))
        tenant = res.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                name="GHR Demo Organization",
                slug="ghr-demo",
                tier="enterprise",
                is_active=True,
                config={}
            )
            session.add(tenant)
            await session.flush()
            print(f"Created Tenant: {tenant.slug} ({tenant.id})")
        else:
            print(f"Tenant exists: {tenant.slug} ({tenant.id})")

        # 2. Create Demo User
        res = await session.execute(select(User).where(User.email == "demo@staffingagent.ai"))
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                tenant_id=tenant.id,
                email="demo@staffingagent.ai",
                name="Demo User",
                role="admin",
                password_hash=hash_password("staffing-demo-2026"),
                is_active=True,
                permissions={},
                created_at=datetime.now(timezone.utc)
            )
            session.add(user)
            await session.flush()
            print(f"Created User: {user.email}")
        else:
            # Update password just in case
            user.password_hash = hash_password("staffing-demo-2026")
            user.is_active = True
            print(f"User updated: {user.email}")
        
        await session.commit()
        print("\n--- TEST LOGIN CREDENTIALS ---")
        print(f"Organization: {tenant.slug}")
        print(f"Email:        {user.email}")
        print(f"Password:     staffing-demo-2026")
        print("------------------------------")

if __name__ == "__main__":
    asyncio.run(seed())
