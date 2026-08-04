"""
用户画像服务 — 对应架构图中的「用户与认证服务 (B1)」画像部分

真实数据库实现，对齐 auth_service 的会话自管范式。
"""

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.user import User
from app.services.auth_service import _to_dict


class UserService:
    """用户服务（数据库实现）"""

    @staticmethod
    async def update_profile_tags(user_id: int, tags: dict) -> dict | None:
        """更新用户画像标签（合并写入 profile_tags JSON 列）。用户不存在返回 None。"""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                return None
            # 合并更新；JSON 列不追踪原地修改，必须赋一个新 dict 才能触发持久化
            merged = dict(user.profile_tags or {})
            for key in ["tech_stack", "interests", "status", "experience_level"]:
                if key in tags and tags[key] is not None:
                    merged[key] = tags[key]
            user.profile_tags = merged
            await session.commit()
            await session.refresh(user)
            return _to_dict(user)

    @staticmethod
    async def get_profile(user_id: int) -> dict | None:
        """获取用户完整画像。"""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            return _to_dict(user) if user is not None else None

    @staticmethod
    async def get_public_profile(user_id: int) -> dict | None:
        """获取用户公开信息（不含敏感字段）。"""
        user = await UserService.get_profile(user_id)
        if user:
            public = dict(user)
            public.pop("hashed_password", None)
            return public
        return None


user_service = UserService()
