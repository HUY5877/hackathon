"""
用户模型 — 对应架构图中的「用户与认证服务」
"""

import enum
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Enum, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(str, enum.Enum):
    VISITOR = "visitor"       # 游客
    DEVELOPER = "developer"   # 已注册开发者
    ADMIN = "admin"           # 管理员


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # 角色
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VISITOR)

    # 用户画像标签（JSON 存储）
    # 示例: {"tech_stack": ["Python", "React"], "interests": ["AI", "Web3"], "status": "student"}
    profile_tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 订阅状态
    edm_subscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"