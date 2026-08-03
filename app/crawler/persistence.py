"""
爬虫数据持久化管道 — 将清洗后的标准化数据写入数据库

职责：
1. 将 StandardizedHackathon 列表转换为 Hackathon ORM 对象
2. 检查数据库中已存在的记录（基于 source_url / slug）
3. 执行 upsert（更新或插入），避免重复
4. 返回写入统计

设计原则：
- 幂等：重复运行不会产生重复记录
- 增量更新：已存在的记录会合并新字段（仅补充空字段）
- 软冲突：source_url 相同视为同一条赛事，更新而非插入
"""

import logging
from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.llm_processor import StandardizedHackathon
from app.crawler.mapper import to_hackathon_orm, parse_date, normalize_mode, normalize_status, compute_status_from_dates
from app.models.hackathon import Hackathon, HackathonStatus

logger = logging.getLogger(__name__)


class PersistenceResult:
    """持久化结果统计"""

    def __init__(self):
        self.inserted = 0
        self.updated = 0
        self.skipped = 0
        self.errors: list[str] = []
        self.total = 0

    def to_dict(self) -> dict:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
            "total": self.total,
        }

    def __repr__(self) -> str:
        return (
            f"<PersistenceResult inserted={self.inserted} updated={self.updated} "
            f"skipped={self.skipped} errors={len(self.errors)}>"
        )


async def _fetch_existing_by_source_url(
    session: AsyncSession,
    source_urls: list[str],
) -> dict[str, Hackathon]:
    """根据 source_url 批量查询已存在的记录"""
    if not source_urls:
        return {}
    stmt = select(Hackathon).where(Hackathon.source_url.in_(source_urls))
    result = await session.execute(stmt)
    return {h.source_url: h for h in result.scalars().all()}


async def _fetch_existing_slugs(session: AsyncSession) -> set[str]:
    """查询数据库中所有已存在的 slug"""
    stmt = select(Hackathon.slug)
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


def _merge_existing(existing: Hackathon, new_orm: Hackathon) -> bool:
    """将新数据合并到已存在的记录中（仅补充空字段）

    Returns:
        True 表示有字段被更新，False 表示无变化
    """
    changed = False

    # 文本字段：仅补充空值
    for field in ["description", "summary", "prize_pool", "location",
                  "country", "city", "organizer", "registration_url"]:
        if not getattr(existing, field, None):
            new_val = getattr(new_orm, field, None)
            if new_val:
                setattr(existing, field, new_val)
                changed = True

    # 日期字段：仅补充空值
    for field in ["registration_start", "registration_end",
                  "event_start", "event_end"]:
        if getattr(existing, field, None) is None:
            new_val = getattr(new_orm, field, None)
            if new_val is not None:
                setattr(existing, field, new_val)
                changed = True

    # 数值字段：取较大值或补充空值
    if not existing.prize_pool_usd and new_orm.prize_pool_usd:
        existing.prize_pool_usd = new_orm.prize_pool_usd
        changed = True
    if not existing.expected_participants and new_orm.expected_participants:
        existing.expected_participants = new_orm.expected_participants
        changed = True

    # 列表字段：合并去重
    for field in ["track_tags", "tech_tags", "sponsors"]:
        existing_list = getattr(existing, field, None) or []
        new_list = getattr(new_orm, field, None) or []
        if new_list:
            merged = list(dict.fromkeys(existing_list + new_list))
            if len(merged) > len(existing_list):
                setattr(existing, field, merged)
                changed = True

    # 置信度：取较高值
    if new_orm.llm_confidence and (
        not existing.llm_confidence or new_orm.llm_confidence > existing.llm_confidence
    ):
        existing.llm_confidence = new_orm.llm_confidence
        changed = True

    # 图片：优先保留已有封面，新数据补充
    if not existing.cover_image and new_orm.cover_image:
        existing.cover_image = new_orm.cover_image
        changed = True

    # raw_data：合并（新数据覆盖同 key）
    if new_orm.raw_data:
        existing_raw = dict(existing.raw_data or {})
        existing_raw.update(new_orm.raw_data)
        existing.raw_data = existing_raw
        changed = True

    # 状态：如果原状态是 UPCOMING 但新数据有更准确的状态，更新
    if existing.status == HackathonStatus.UPCOMING and new_orm.status != HackathonStatus.UPCOMING:
        existing.status = new_orm.status
        changed = True

    return changed


async def persist_batch(
    session: AsyncSession,
    items: list[StandardizedHackathon],
    skip_low_confidence: bool = False,
    min_confidence: float = 0.3,
) -> PersistenceResult:
    """将标准化数据批量写入数据库

    Args:
        session: 异步数据库会话
        items: LLM 清洗后的标准化数据列表
        skip_low_confidence: 是否跳过低置信度数据
        min_confidence: 最低置信度阈值（仅 skip_low_confidence=True 时生效）

    Returns:
        PersistenceResult 统计对象
    """
    result = PersistenceResult()
    result.total = len(items)

    if not items:
        return result

    # 1. 收集所有 source_url，批量查询已存在记录
    source_urls = [item.source_url for item in items if item.source_url]
    existing_map = await _fetch_existing_by_source_url(session, source_urls)

    # 2. 查询所有已存在 slug（用于新插入时的唯一性检查）
    existing_slugs = await _fetch_existing_slugs(session)

    # 3. 逐条处理
    for item in items:
        try:
            # 跳过低置信度
            if skip_low_confidence and (item.llm_confidence or 0) < min_confidence:
                result.skipped += 1
                logger.debug(f"[persistence] 跳过低置信度: {item.name} (conf={item.llm_confidence})")
                continue

            # 跳过无名称的无效数据
            if not item.name or not item.name.strip():
                result.skipped += 1
                logger.debug(f"[persistence] 跳过无名称数据: {item.source_url}")
                continue

            # 已存在 → 更新
            if item.source_url and item.source_url in existing_map:
                existing = existing_map[item.source_url]
                new_orm = to_hackathon_orm(item, existing_slugs=existing_slugs)
                changed = _merge_existing(existing, new_orm)
                if changed:
                    result.updated += 1
                else:
                    result.skipped += 1
                continue

            # 新记录 → 插入
            new_orm = to_hackathon_orm(item, existing_slugs=existing_slugs)
            existing_slugs.add(new_orm.slug)
            session.add(new_orm)
            result.inserted += 1

        except Exception as e:
            result.errors.append(f"{item.name}: {e}")
            logger.error(f"[persistence] 写入失败 {item.name}: {e}")

    # 4. 提交事务
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"[persistence] 批量提交失败: {e}")
        result.errors.append(f"commit_failed: {e}")

    logger.info(
        f"[persistence] 完成: 插入 {result.inserted}, 更新 {result.updated}, "
        f"跳过 {result.skipped}, 错误 {len(result.errors)}"
    )
    return result


async def persist_single(
    session: AsyncSession,
    item: StandardizedHackathon,
) -> PersistenceResult:
    """写入单条数据（便捷方法）"""
    return await persist_batch(session, [item])
