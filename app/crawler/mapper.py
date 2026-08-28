"""
爬虫数据 → ORM 映射器

将 LLM 清洗后的 StandardizedHackathon 转换为 Hackathon ORM 对象，
处理字段类型差异（str → datetime / Enum）、缺失字段默认值、slug 唯一性。
"""

import logging
import re
from datetime import datetime
from typing import Iterable

from app.crawler.base import CrawlResult
from app.crawler.llm_processor import StandardizedHackathon
from app.models.hackathon import Hackathon, HackathonMode, HackathonStatus

logger = logging.getLogger(__name__)


def _make_slug(name: str) -> str:
    """Build the stable slug required by persistence without calling an LLM."""
    slug = name.lower().replace(" ", "-").replace("/", "-")
    slug = re.sub(r"[^\w\u4e00-\u9fff\-]", "", slug, flags=re.UNICODE)
    return slug[:500] or "untitled"


def crawl_result_to_standardized(result: CrawlResult) -> StandardizedHackathon:
    """Map crawler output into the persistence DTO using source data only.

    This function deliberately performs no network or model calls. LLM screening
    and presentation cleanup start only after the row has been persisted.
    """
    raw = dict(result.raw_data or {})
    name = raw.get("title") or raw.get("name") or result.raw_title or "未命名活动"
    description = raw.get("description") or result.raw_description
    image_urls = list(dict.fromkeys(result.image_urls or raw.get("image_urls") or []))

    return StandardizedHackathon(
        name=name,
        slug=_make_slug(name),
        description=description,
        summary=raw.get("summary"),
        registration_start=raw.get("signup_start") or raw.get("registration_start"),
        registration_end=raw.get("signup_end") or raw.get("registration_end"),
        event_start=raw.get("start_date") or raw.get("event_start"),
        event_end=raw.get("end_date") or raw.get("event_end"),
        status=raw.get("status") or "upcoming",
        mode=raw.get("mode") or "online",
        track_tags=raw.get("tracks") or raw.get("track_tags") or [],
        tech_tags=raw.get("tech_tags") or [],
        prize_pool=raw.get("prize") or raw.get("prize_pool"),
        prize_pool_usd=raw.get("prize_pool_usd"),
        location=raw.get("location"),
        country=raw.get("country"),
        city=raw.get("city"),
        source_url=result.source_url,
        source_platform=result.source_platform,
        organizer=raw.get("organizer"),
        sponsors=raw.get("sponsors") or [],
        requirements=raw.get("requirements") or [],
        timeline=raw.get("timeline") or [],
        rules=raw.get("rules"),
        raw_data=raw,
        cover_image=raw.get("cover_image"),
        image_urls=image_urls,
    )


# ── 日期解析 ──────────────────────────────────────────

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y年%m月%d日",
    "%B %d, %Y",       # January 15, 2026
    "%b %d, %Y",       # Jan 15, 2026
    "%d %B %Y",        # 15 January 2026
    "%d %b %Y",        # 15 Jan 2026
]


def parse_date(value: str | None) -> datetime | None:
    """尝试多种格式解析日期字符串

    支持 ISO、中文、英文等多种格式。无法解析时返回 None。
    """
    if not value or not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    # 尝试已知格式
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # 尝试从混合文本中提取 YYYY-MM-DD
    match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if match:
        y, m, d = match.groups()
        try:
            return datetime(int(y), int(m), int(d))
        except ValueError:
            pass

    # 尝试 ISO 格式（带时区或毫秒）
    try:
        # 截断毫秒/微秒
        iso_text = re.sub(r"(\.\d+)?([+-]\d{2}:?\d{2}|Z)$", "", text)
        return datetime.fromisoformat(iso_text)
    except (ValueError, TypeError):
        pass

    logger.debug(f"[mapper] 无法解析日期: {value!r}")
    return None


# ── 枚举映射 ──────────────────────────────────────────

_MODE_MAP = {
    "online": HackathonMode.ONLINE,
    "offline": HackathonMode.OFFLINE,
    "in-person": HackathonMode.OFFLINE,
    "physical": HackathonMode.OFFLINE,
    "hybrid": HackathonMode.HYBRID,
    "mixed": HackathonMode.HYBRID,
}

_STATUS_MAP = {
    "upcoming": HackathonStatus.UPCOMING,
    "registering": HackathonStatus.REGISTERING,
    "open": HackathonStatus.REGISTERING,
    "ongoing": HackathonStatus.ONGOING,
    "active": HackathonStatus.ONGOING,
    "ended": HackathonStatus.ENDED,
    "closed": HackathonStatus.ENDED,
    "finished": HackathonStatus.ENDED,
}


def normalize_mode(mode: str | None) -> HackathonMode:
    if not mode:
        return HackathonMode.ONLINE
    return _MODE_MAP.get(mode.lower().strip(), HackathonMode.ONLINE)


def normalize_status(status: str | None) -> HackathonStatus:
    if not status:
        return HackathonStatus.UPCOMING
    return _STATUS_MAP.get(status.lower().strip(), HackathonStatus.UPCOMING)


def compute_status_from_dates(
    registration_end: datetime | None,
    event_start: datetime | None,
    event_end: datetime | None,
    now: datetime | None = None,
) -> HackathonStatus:
    """根据日期推断状态（当原始数据未提供 status 时）"""
    now = now or datetime.now()
    if event_end and now > event_end:
        return HackathonStatus.ENDED
    if event_start and now >= event_start:
        return HackathonStatus.ONGOING
    if registration_end and now > registration_end:
        return HackathonStatus.UPCOMING  # 报名截止但活动未开始
    if registration_end or event_start:
        return HackathonStatus.REGISTERING
    return HackathonStatus.UPCOMING


# ── slug 唯一性处理 ───────────────────────────────────

def ensure_unique_slug(slug: str, existing_slugs: Iterable[str]) -> str:
    """确保 slug 唯一，冲突时追加 -2 / -3 后缀"""
    existing_set = set(existing_slugs)
    if slug not in existing_set:
        return slug
    base = slug
    suffix = 2
    while f"{base}-{suffix}" in existing_set:
        suffix += 1
    return f"{base}-{suffix}"


# ── 主映射函数 ────────────────────────────────────────

def to_hackathon_orm(
    item: StandardizedHackathon,
    existing_slugs: Iterable[str] | None = None,
) -> Hackathon:
    """将 StandardizedHackathon 转换为 Hackathon ORM 对象

    Args:
        item: LLM 清洗后的标准化数据
        existing_slugs: 已存在的 slug 集合，用于冲突检测
    """
    # 解析日期
    reg_start = parse_date(item.registration_start)
    reg_end = parse_date(item.registration_end)
    evt_start = parse_date(item.event_start)
    evt_end = parse_date(item.event_end)

    # 状态：优先用原始值，无法映射时按日期推断
    status = normalize_status(item.status)
    if status == HackathonStatus.UPCOMING and (reg_end or evt_start or evt_end):
        status = compute_status_from_dates(reg_end, evt_start, evt_end)

    # slug 唯一性
    slug = item.slug or "untitled"
    if existing_slugs is not None:
        slug = ensure_unique_slug(slug, existing_slugs)

    # 报名链接：优先从 raw_data 提取
    registration_url = item.raw_data.get("signup_url") or item.raw_data.get("registration_url")

    # 预计参与人数
    expected_participants = item.raw_data.get("participants_count")

    # 构建 raw_data：将 LLM 提取但 ORM 无对应列的字段保留下来
    raw_data = dict(item.raw_data)
    if item.requirements:
        raw_data["_requirements"] = item.requirements
    if item.timeline:
        raw_data["_timeline"] = item.timeline
    if item.rules:
        raw_data["_rules"] = item.rules
    # 保留图片列表（ORM 只有 cover_image，其余放 raw_data）
    if item.image_urls:
        raw_data["_image_urls"] = item.image_urls

    return Hackathon(
        name=item.name,
        slug=slug,
        description=item.description,
        summary=item.summary,
        registration_start=reg_start,
        registration_end=reg_end,
        event_start=evt_start,
        event_end=evt_end,
        status=status,
        mode=normalize_mode(item.mode),
        track_tags=item.track_tags or None,
        tech_tags=item.tech_tags or None,
        prize_pool=item.prize_pool,
        prize_pool_usd=item.prize_pool_usd,
        expected_participants=expected_participants,
        location=item.location,
        country=item.country,
        city=item.city,
        source_url=item.source_url,
        source_platform=item.source_platform,
        registration_url=registration_url,
        organizer=item.organizer,
        sponsors=item.sponsors or None,
        cover_image=item.cover_image,  # ← 新增：封面图
        is_verified=False,
        llm_confidence=item.llm_confidence,
        raw_data=raw_data,
    )


def to_hackathon_orm_batch(
    items: list[StandardizedHackathon],
) -> list[Hackathon]:
    """批量转换，自动处理批次内 slug 冲突

    注意：此函数仅在当前批次内去重 slug，不查询数据库。
    如需避免与数据库已有记录冲突，请使用 persistence.persist_batch，
    它会先查询数据库已存在的 slug，再传递给 to_hackathon_orm。
    """
    existing_slugs: set[str] = set()
    results: list[Hackathon] = []
    for item in items:
        orm = to_hackathon_orm(item, existing_slugs=existing_slugs)
        existing_slugs.add(orm.slug)
        results.append(orm)
    return results
