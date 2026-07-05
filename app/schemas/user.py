"""用户 Schema — 注册、登录、画像标签、EDM 订阅"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── 请求 ────────────────────────────────────

class UserRegisterRequest(BaseModel):
    """用户注册请求"""

    email: EmailStr = Field(
        description="用户邮箱地址，用于登录和接收 EDM 通知",
    )
    username: str = Field(
        min_length=2,
        max_length=50,
        description="用户昵称，2-50 个字符，平台内唯一",
    )
    password: str = Field(
        min_length=6,
        max_length=100,
        description="登录密码，6-100 个字符",
    )


class UserLoginRequest(BaseModel):
    """用户登录请求"""

    email: EmailStr = Field(
        description="注册时使用的邮箱地址",
    )
    password: str = Field(
        description="登录密码",
    )


class UserProfileTagsUpdate(BaseModel):
    """
    用户画像标签更新

    对应 PRD 模块二的「极简用户画像构建」：
    新用户注册后通过标签选择向导收集偏好，用于个性化推荐
    """

    tech_stack: list[str] | None = Field(
        default=None,
        description="技术栈标签，如 ['Python', 'React', 'Solidity', 'Go']",
    )
    interests: list[str] | None = Field(
        default=None,
        description="兴趣方向标签，如 ['AI', 'Web3', 'Cloud Native', '游戏开发']",
    )
    status: str | None = Field(
        default=None,
        description="身份状态: 'student'(在校生) / 'professional'(职场人) / 'freelancer'(自由职业)",
    )
    experience_level: str | None = Field(
        default=None,
        description="经验水平: 'beginner'(新手) / 'intermediate'(进阶) / 'advanced'(资深)",
    )


class EDMSubscribeRequest(BaseModel):
    """EDM 邮件订阅开关请求"""

    subscribed: bool = Field(
        description="是否订阅邮件通知，true 开启 / false 关闭",
    )


# ── 响应 ────────────────────────────────────

class UserProfileResponse(BaseModel):
    """用户画像响应（公开信息，不含密码）"""

    id: int = Field(description="用户唯一 ID")
    email: str = Field(description="用户邮箱")
    username: str = Field(description="用户昵称")
    role: str = Field(description="用户角色: 'visitor'(游客) / 'developer'(开发者) / 'admin'(管理员)")
    profile_tags: dict | None = Field(
        default=None,
        description="用户画像标签，包含 tech_stack / interests / status / experience_level",
    )
    edm_subscribed: bool = Field(description="是否已订阅 EDM 赛事上新邮件通知")
    email_verified: bool = Field(description="邮箱是否已验证")
    created_at: datetime = Field(description="账号注册时间")

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """登录/注册成功后的 Token 响应"""

    access_token: str = Field(
        description="JWT 访问令牌，后续请求需在 Authorization Header 中携带（Bearer <token>）",
    )
    token_type: str = Field(
        default="bearer",
        description="Token 类型，固定为 'bearer'",
    )
    user: UserProfileResponse = Field(description="当前登录用户的基本信息")