"""
用户与认证服务 — 对应架构图中的「用户与认证服务 (B1)」
目前为 Mock 实现，后续对接数据库和 JWT
"""
from datetime import datetime, timedelta

from app.config import settings

# ── Mock 数据 ─────────────────────────────────────────────────────────

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


class AuthService:
    """认证服务（Mock 实现）"""

    @staticmethod
    async def register(email: str, username: str, password: str) -> dict | None:
        """注册新用户"""
        # Mock: 检查是否已存在
        for u in MOCK_USERS:
            if u["email"] == email or u["username"] == username:
                return None
        new_user = {
            "id": len(MOCK_USERS) + 1,
            "email": email,
            "username": username,
            "hashed_password": f"$2b$12$mock_{password}",
            "role": "developer",
            "profile_tags": None,
            "edm_subscribed": False,
            "email_verified": False,
            "created_at": datetime.now(),
        }
        MOCK_USERS.append(new_user)
        return new_user

    @staticmethod
    async def login(email: str, password: str) -> dict | None:
        """登录验证"""
        for u in MOCK_USERS:
            if u["email"] == email:
                # Mock: 跳过真实密码验证
                return u
        return None

    @staticmethod
    async def get_user_by_id(user_id: int) -> dict | None:
        """根据 ID 获取用户"""
        for u in MOCK_USERS:
            if u["id"] == user_id:
                return u
        return None

    @staticmethod
    def create_access_token(user_id: int) -> str:
        """生成 JWT Token（Mock 实现）"""
        # 生产环境使用 python-jose 签发真实 JWT
        import base64
        import json
        payload = {
            "sub": str(user_id),
            "exp": int((datetime.now() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
            "iat": int(datetime.now().timestamp()),
        }
        # Mock: 简单 base64 编码（生产环境替换为 JWT 签名）
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        return f"mock_jwt_{payload_b64}"

    @staticmethod
    async def decode_token(token: str) -> int | None:
        """解析 JWT Token 获取 user_id（Mock 实现）"""
        if not token.startswith("mock_jwt_"):
            return None
        try:
            import base64
            import json
            payload_b64 = token[len("mock_jwt_"):]
            payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()))
            # 检查是否过期
            if payload.get("exp", 0) < datetime.now().timestamp():
                return None
            return int(payload.get("sub", 0))
        except Exception:
            return None


auth_service = AuthService()