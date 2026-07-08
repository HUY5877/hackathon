"""
灵感池内容模型 — 对应架构图中的「专属灵感池」
PGC 精选内容：往期黑客松获奖案例深度拆解
"""

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Integer, func, Text, JSON
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InspirationItem(Base):
    """灵感池内容条目"""

    __tablename__ = "inspiration_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)

    # ── 内容分层（注册墙机制） ─────────────────
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)    # 公开摘要（游客可见）
    full_content: Mapped[str | None] = mapped_column(Text, nullable=True)  # 完整内容（需登录）
    # 核心干货摘要，用于注册墙拦截页的诱饵文案
    teaser: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── 来源信息 ──────────────────────────────
    source_hackathon_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_hackathon_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    team_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prize_won: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # ── 结构化分类标签 ────────────────────────
    # 如: ["AI应用", "Web3", "开发者工具", "生活方式", "教育科技"]
    category_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    tech_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    difficulty_level: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "beginner" / "intermediate" / "advanced"

    # ── 团队画像（用于启发用户组队） ──────────
    # 如: {"size": 4, "roles": ["前端", "后端", "设计师", "产品"], "background": "3名在校生+1名职场人"}
    team_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── 媒体资源 ──────────────────────────────
    cover_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_code_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    demo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # ── 互动数据 ──────────────────────────────
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    bookmark_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── 发布状态 ──────────────────────────────
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否精选推荐

    # ── 时间戳 ────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<InspirationItem(id={self.id}, title={self.title})>"


class UserInteraction(Base):
    """用户与灵感内容的交互记录（点赞 / 收藏 / 外链点击）"""

    __tablename__ = "user_interactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)  # inspiration_items.id
    interaction_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "like" / "bookmark" / "click"

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<UserInteraction(user={self.user_id}, item={self.item_id}, type={self.interaction_type})>"