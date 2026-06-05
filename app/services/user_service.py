"""
用户画像服务 — 对应架构图中的「用户与认证服务 (B1)」画像部分
"""

from app.services.auth_service import MOCK_USERS


class UserService:
    """用户服务（Mock 实现）"""

    @staticmethod
    async def update_profile_tags(user_id: int, tags: dict) -> dict | None:
        """更新用户画像标签"""
        for user in MOCK_USERS:
            if user["id"] == user_id:
                current_tags = user.get("profile_tags") or {}
                # 合并更新
                for key in ["tech_stack", "interests", "status", "experience_level"]:
                    if key in tags and tags[key] is not None:
                        current_tags[key] = tags[key]
                user["profile_tags"] = current_tags
                return dict(user)
        return None

    @staticmethod
    async def get_profile(user_id: int) -> dict | None:
        """获取用户完整画像"""
        for user in MOCK_USERS:
            if user["id"] == user_id:
                return dict(user)
        return None

    @staticmethod
    async def get_public_profile(user_id: int) -> dict | None:
        """获取用户公开信息（不含敏感字段）"""
        user = await UserService.get_profile(user_id)
        if user:
            public = dict(user)
            public.pop("hashed_password", None)
            return public
        return None


user_service = UserService()