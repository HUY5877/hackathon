"""初始化数据库 - 创建所有表"""
import asyncio
import sys

from app.db.session import Base, engine
from app.models import Hackathon, User, InspirationItem, EmpowermentArticle


async def init_db():
    print("开始创建数据库表...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 建表成功")

    # 列出所有表
    from sqlalchemy import inspect
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        print(f"📊 数据库表: {tables}")

        # 列出 hackathons 表的字段
        from app.models.hackathon import Hackathon
        cols = await conn.run_sync(
            lambda sync_conn: [
                (c["name"], str(c["type"]), c.get("nullable", True))
                for c in inspect(sync_conn).get_columns("hackathons")
            ]
        )
        print("\n📋 hackathons 表字段:")
        for name, typ, nullable in cols:
            print(f"  {name:30s} {typ:30s} nullable={nullable}")


if __name__ == "__main__":
    asyncio.run(init_db())
