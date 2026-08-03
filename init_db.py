"""容器启动时初始化数据库表"""
import asyncio
from app.db.session import engine, Base
from app.models import hackathon, user, inspiration, empowerment  # noqa: F401 — 注册所有模型


async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables ready")


if __name__ == "__main__":
    asyncio.run(init())
