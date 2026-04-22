import asyncio
from sqlalchemy import text
from app_platform.api.database import engine

async def check_tenants():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT slug FROM tenants"))
        tenants = res.fetchall()
        print(f"Tenants: {tenants}")

if __name__ == "__main__":
    asyncio.run(check_tenants())
