"""
信息大厅服务 — 对应架构图中的「内容调度服务 (B2)」
管理黑客松赛事数据的查询、筛选与交互（数据库实现）
"""

from datetime import datetime

from sqlalchemy import select, func, update, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.models.hackathon import (
    Hackathon,
    HackathonDisplayStatus,
    HackathonMode,
    HackathonStatus,
)


def _public_visibility_conditions():
    """Return the minimum conditions shared by every public event query."""
    return (
        Hackathon.display_status == HackathonDisplayStatus.APPROVED,
        Hackathon.is_cleaned.is_(True),
        or_(Hackathon.event_start.is_not(None), Hackathon.event_end.is_not(None)),
    )


class HackathonService:
    """信息大厅服务（数据库实现）"""

    @staticmethod
    async def list_hackathons(
        status: str | None = None,
        mode: str | None = None,
        track_tags: list[str] | None = None,
        tech_tags: list[str] | None = None,
        country: str | None = None,
        keyword: str | None = None,
        sort_by: str = "event_start",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """获取黑客松列表（支持多维筛选）"""
        async with async_session_factory() as session:
            # 基础查询
            query = select(Hackathon)
            count_query = select(func.count(Hackathon.id))

            # ── 筛选条件 ──
            conditions = list(_public_visibility_conditions())
            if status:
                conditions.append(Hackathon.status == status.upper())
            if mode:
                conditions.append(Hackathon.mode == mode.upper())
            if country:
                conditions.append(Hackathon.country == country)
            if track_tags:
                # track_tags 是 ARRAY 类型，检查是否有交集
                for tag in track_tags:
                    conditions.append(Hackathon.track_tags.any(tag))
            if tech_tags:
                for tag in tech_tags:
                    conditions.append(Hackathon.tech_tags.any(tag))
            if keyword:
                kw = f"%{keyword}%"
                conditions.append(
                    or_(
                        Hackathon.name.ilike(kw),
                        Hackathon.summary.ilike(kw),
                        Hackathon.description.ilike(kw),
                    )
                )

            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

            # ── 排序 ──
            sort_map = {
                "prize_pool_usd": Hackathon.prize_pool_usd.desc().nullslast(),
                "view_count": Hackathon.view_count.desc(),
                "created_at": Hackathon.created_at.desc(),
                "event_start": Hackathon.event_start.asc().nullslast(),
            }
            order_by = sort_map.get(sort_by, Hackathon.event_start.asc().nullslast())
            query = query.order_by(order_by)

            # ── 分页 ──
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

            # ── 执行 ──
            result = await session.execute(query)
            rows = result.scalars().all()

            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

        items = [HackathonService._to_dict(h) for h in rows]
        return items, total

    @staticmethod
    async def get_hackathon(slug: str) -> dict | None:
        """获取黑客松详情"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon).where(
                    Hackathon.slug == slug,
                    *_public_visibility_conditions(),
                )
            )
            hackathon = result.scalar_one_or_none()
            if hackathon is None:
                return None
            return HackathonService._to_dict(hackathon)

    @staticmethod
    async def record_external_click(hackathon_id: int) -> dict:
        """记录外链点击（更新数据库中的 external_click_count）"""
        async with async_session_factory() as session:
            await session.execute(
                update(Hackathon)
                .where(
                    Hackathon.id == hackathon_id,
                    *_public_visibility_conditions(),
                )
                .values(external_click_count=Hackathon.external_click_count + 1)
            )
            await session.commit()

            # 读取更新后的值
            result = await session.execute(
                select(Hackathon.external_click_count).where(
                    Hackathon.id == hackathon_id,
                    *_public_visibility_conditions(),
                )
            )
            count = result.scalar() or 0
            return {"click_id": count, "hackathon_id": hackathon_id}

    @staticmethod
    async def get_hot_list(limit: int = 5) -> list[dict]:
        """获取综合热度榜单（按浏览量倒序）"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon)
                .where(*_public_visibility_conditions())
                .order_by(Hackathon.view_count.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
        return [HackathonService._to_dict(h) for h in rows]

    @staticmethod
    def _to_dict(h: Hackathon) -> dict:
        """将 ORM 模型转为字典（供 Schema 序列化）"""
        return {
            "id": h.id,
            "name": h.name,
            "slug": h.slug,
            "description": h.description,
            "summary": h.summary,
            "registration_start": h.registration_start,
            "registration_end": h.registration_end,
            "event_start": h.event_start,
            "event_end": h.event_end,
            "status": h.status.value.lower() if h.status else None,
            "mode": h.mode.value.lower() if h.mode else None,
            "track_tags": h.track_tags,
            "tech_tags": h.tech_tags,
            "prize_pool": h.prize_pool,
            "prize_pool_usd": h.prize_pool_usd,
            "expected_participants": h.expected_participants,
            "location": h.location,
            "country": h.country,
            "city": h.city,
            "source_url": h.source_url,
            "source_platform": h.source_platform,
            "registration_url": h.registration_url,
            "organizer": h.organizer,
            "sponsors": h.sponsors,
            "is_verified": h.is_verified,
            "view_count": h.view_count,
            "external_click_count": h.external_click_count,
            "created_at": h.created_at,
        }


hackathon_service = HackathonService()
