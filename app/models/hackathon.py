"""
黑客松赛事模型 — 对应架构图中的「信息大厅」与「自动化引擎」
"""

import enum
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Enum, JSON, Float, func, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY

from app.db import Base


class HackathonMode(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    HYBRID = "hybrid"


class HackathonStatus(str, enum.Enum):
    UPCOMING = "upcoming"       # 即将开始
    REGISTERING = "registering" # 报名中
    ONGOING = "ongoing"         # 进行中
    ENDED = "ended"             # 已结束


class Hackathon(Base):
    """黑客松赛事 — 经过 LLM 清洗后的标准化字段"""

    __tablename__ = "hackathons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── 核心字段 ──────────────────────────────
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)  # LLM 生成的摘要

    # ── 时间线 ────────────────────────────────
    registration_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    registration_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    event_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    event_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[HackathonStatus] = mapped_column(
        Enum(HackathonStatus), default=HackathonStatus.UPCOMING, index=True
    )

    # ── 分类标签 ──────────────────────────────
    mode: Mapped[HackathonMode] = mapped_column(Enum(HackathonMode), default=HackathonMode.ONLINE)
    # 赛道标签: ["AI", "Web3", "Cloud Native", "IoT", ...]
    track_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    # 技术栈标签: ["Python", "Solidity", "React", ...]
    tech_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # ── 奖金与规模 ────────────────────────────
    prize_pool: Mapped[str | None] = mapped_column(String(200), nullable=True)  # "¥50,000" / "$10,000 USD"
    prize_pool_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # 标准化 USD 金额
    expected_participants: Mapped[int | None] = mapped_column(nullable=True)

    # ── 地理信息 ──────────────────────────────
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── 来源溯源 ──────────────────────────────
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)  # 原始页面 URL
    source_platform: Mapped[str] = mapped_column(String(100), nullable=False)  # "devpost" / "mlh" / "dorahacks"
    registration_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # 官方报名链接

    # ── 主办方信息 ────────────────────────────
    organizer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sponsors: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # ── 数据质量 ──────────────────────────────
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否经人工审核
    llm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # LLM 提取置信度
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 原始抓取数据（备份）

    # ── 平台统计 ──────────────────────────────
    view_count: Mapped[int] = mapped_column(default=0)
    external_click_count: Mapped[int] = mapped_column(default=0)  # 外链点击转化数

    # ── 时间戳 ────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Hackathon(id={self.id}, name={self.name}, status={self.status})>"