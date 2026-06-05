"""
开发者赋能内容模型 — 对应架构图中的「开发者赋能区」
Vibecoding 教程 + 新手参赛指南
"""

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Integer, func, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ContentType:
    VIBECODING = "vibecoding"       # AI 辅助编程教程
    GUIDE = "guide"                 # 新手参赛指南 / 软技能


class EmpowermentArticle(Base):
    """赋能文章"""

    __tablename__ = "empowerment_articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)

    # ── 内容类型 ──────────────────────────────
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # "vibecoding" → AI 辅助编程教程
    # "guide"      → 黑客松软技能指南

    # ── 子分类 ────────────────────────────────
    # vibecoding: "cursor" / "copilot" / "chatgpt" / "windsurf" / "general"
    # guide:       "teaming" / "pitch_deck" / "process" / "mentor_tips"
    sub_category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── 内容 ──────────────────────────────────
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 难度等级 ──────────────────────────────
    difficulty_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    estimated_read_time: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 预计阅读时长（分钟）

    # ── 标签 ──────────────────────────────────
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # ── 媒体 ──────────────────────────────────
    cover_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # 外部链接（如 YouTube 教程）

    # ── 互动数据 ──────────────────────────────
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── 发布状态 ──────────────────────────────
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 时间戳 ────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<EmpowermentArticle(id={self.id}, title={self.title}, type={self.content_type})>"