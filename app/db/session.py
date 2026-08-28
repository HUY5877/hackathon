"""数据库引擎与会话管理"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# SQL 明细会淹没爬虫和筛选任务的业务日志；需要排查 SQL 时临时调整
# sqlalchemy.engine 的日志级别即可。
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

# 会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
