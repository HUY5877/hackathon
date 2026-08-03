"""用户与认证服务 — 真实数据库实现。

对齐 hackathon_service 的既定范式：service 方法内部用
`async with async_session_factory()` 自管会话，路由/依赖无需注入 db。
"""

from datetime import datetime

from sqlalchemy import select, or_

from app.db.session import async_session_factory
from app.models.user import User, UserRole
from app.core import security

# ── 遗留 Mock 数据（兼容垫片）────────────────────────────────────────
# recommendation_service / edm_service / user_service 仍是 Mock 实现，
# 它们 `from app.services.auth_service import MOCK_USERS`。auth 已改为真实 DB，
# 这里保留该列表仅为让上述 Mock 模块继续工作（零回归）；待其迁移到 DB 后删除。
MOCK_USERS: list[dict] = [
    {
        "id": 1,
        "email": "developer@example.com",
        "username": "DevXiaoWang",
        "hashed_password": "$2b$12$mock_hashed_password_123456",
        "role": "developer",
        "profile_tags": {
            "tech_stack": ["Python", "React", "Solidity"],
            "interests": ["AI", "Web3"],
            "status": "student",
            "experience_level": "intermediate",
        },
        "edm_subscribed": True,
        "email_verified": True,
        "created_at": datetime(2026, 5, 15, 10, 30),
    },
    {
        "id": 2,
        "email": "newbie@example.com",
        "username": "NewbieXiaoLi",
        "hashed_password": "$2b$12$mock_hashed_password_789012",
        "role": "developer",
        "profile_tags": {
            "tech_stack": ["JavaScript", "HTML/CSS"],
            "interests": ["Web Development", "AI"],
            "status": "student",
            "experience_level": "beginner",
        },
        "edm_subscribed": False,
        "email_verified": True,
        "created_at": datetime(2026, 5, 20, 14, 0),
    },
    {
        "id": 3,
        "email": "admin@example.com",
        "username": "Admin",
        "hashed_password": "$2b$12$mock_hashed_password_admin",
        "role": "admin",
        "profile_tags": None,
        "edm_subscribed": True,
        "email_verified": True,
        "created_at": datetime(2026, 5, 1, 9, 0),
    },
]


def _to_dict(user: User) -> dict:
    """ORM User → dict，字段对齐 UserProfileResponse（含 hashed_password 供内部用）。"""
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "hashed_password": user.hashed_password,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "profile_tags": user.profile_tags,
        "edm_subscribed": user.edm_subscribed,
        "email_verified": user.email_verified,
        "created_at": user.created_at,
    }


class AuthService:
    """认证服务（数据库实现）。"""

    @staticmethod
    async def register(email: str, username: str, password: str) -> dict | None:
        """注册新用户；email 或 username 已存在返回 None。"""
        async with async_session_factory() as session:
            existing = await session.execute(
                select(User).where(or_(User.email == email, User.username == username))
            )
            if existing.scalar_one_or_none() is not None:
                return None
            user = User(
                email=email,
                username=username,
                hashed_password=security.hash_password(password),
                role=UserRole.DEVELOPER,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return _to_dict(user)

    @staticmethod
    async def login(email: str, password: str) -> dict | None:
        """按 email 查用户并校验密码；失败返回 None。"""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if user is None or not security.verify_password(password, user.hashed_password):
                return None
            return _to_dict(user)

    @staticmethod
    async def get_user_by_id(user_id: int) -> dict | None:
        """按 ID 查用户。"""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            return _to_dict(user) if user is not None else None

    @staticmethod
    def create_access_token(user_id: int) -> str:
        """签发 JWT（委托 security）。"""
        return security.create_access_token(user_id)

    @staticmethod
    async def decode_token(token: str) -> int | None:
        """解析 JWT 得 user_id（委托 security）。"""
        return security.decode_access_token(token)


auth_service = AuthService()
