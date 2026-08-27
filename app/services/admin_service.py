"""Database-backed administrator operations."""

from sqlalchemy import and_, func, or_, select

from app.db.session import async_session_factory
from app.models.user import User, UserRole
from app.models.hackathon import (
    Hackathon,
    HackathonDisplayStatus,
    HackathonMode,
    HackathonStatus,
)


class AdminNotFoundError(LookupError):
    """Raised when an administrator target does not exist."""


class AdminConflictError(ValueError):
    """Raised when an administrator action conflicts with current state."""


class AdminValidationError(ValueError):
    """Raised when an update conflicts with the persisted record."""


def _admin_user_dict(user: User) -> dict:
    role = user.role.value if hasattr(user.role, "value") else user.role
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "role": role,
        "email_verified": user.email_verified,
        "created_at": user.created_at,
    }


def _admin_hackathon_dict(hackathon: Hackathon) -> dict:
    status = hackathon.status.value if hasattr(hackathon.status, "value") else hackathon.status
    mode = hackathon.mode.value if hasattr(hackathon.mode, "value") else hackathon.mode
    display_status = (
        hackathon.display_status.value
        if hasattr(hackathon.display_status, "value")
        else hackathon.display_status
    )
    return {
        "id": hackathon.id,
        "name": hackathon.name,
        "slug": hackathon.slug,
        "description": hackathon.description,
        "summary": hackathon.summary,
        "registration_start": hackathon.registration_start,
        "registration_end": hackathon.registration_end,
        "event_start": hackathon.event_start,
        "event_end": hackathon.event_end,
        "status": status,
        "mode": mode,
        "track_tags": hackathon.track_tags,
        "tech_tags": hackathon.tech_tags,
        "prize_pool": hackathon.prize_pool,
        "prize_pool_usd": hackathon.prize_pool_usd,
        "expected_participants": hackathon.expected_participants,
        "location": hackathon.location,
        "country": hackathon.country,
        "city": hackathon.city,
        "source_url": hackathon.source_url,
        "source_platform": hackathon.source_platform,
        "registration_url": hackathon.registration_url,
        "organizer": hackathon.organizer,
        "sponsors": hackathon.sponsors,
        "cover_image": hackathon.cover_image,
        "is_verified": hackathon.is_verified,
        "llm_confidence": hackathon.llm_confidence,
        "display_status": display_status,
        "view_count": hackathon.view_count,
        "external_click_count": hackathon.external_click_count,
        "created_at": hackathon.created_at,
        "updated_at": hackathon.updated_at,
    }


class AdminService:
    """Administrative user and content operations."""

    @staticmethod
    async def list_users(
        *, keyword: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[dict], int]:
        query = select(User)
        count_query = select(func.count(User.id))

        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            pattern = f"%{normalized_keyword}%"
            condition = or_(
                User.email.ilike(pattern),
                User.username.ilike(pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        query = (
            query.order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        async with async_session_factory() as session:
            users_result = await session.execute(query)
            count_result = await session.execute(count_query)
            users = users_result.scalars().all()
            total = count_result.scalar() or 0

        return [_admin_user_dict(user) for user in users], total

    @staticmethod
    async def promote_user(user_id: int) -> dict:
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                raise AdminNotFoundError("用户不存在")

            role = user.role.value if hasattr(user.role, "value") else user.role
            if role == UserRole.ADMIN.value:
                raise AdminConflictError("该用户已经是管理员")

            user.role = UserRole.ADMIN
            await session.commit()
            await session.refresh(user)
            return _admin_user_dict(user)

    @staticmethod
    async def list_hackathons(
        *,
        keyword: str | None = None,
        source_platform: str | None = None,
        status: str | None = None,
        display_status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        conditions = []
        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            pattern = f"%{normalized_keyword}%"
            conditions.append(
                or_(
                    Hackathon.name.ilike(pattern),
                    Hackathon.summary.ilike(pattern),
                    Hackathon.source_platform.ilike(pattern),
                )
            )
        if source_platform:
            conditions.append(Hackathon.source_platform == source_platform)
        if status:
            conditions.append(Hackathon.status == HackathonStatus(status))
        if display_status:
            conditions.append(
                Hackathon.display_status == HackathonDisplayStatus(display_status)
            )

        query = select(Hackathon)
        count_query = select(func.count(Hackathon.id))
        if conditions:
            combined = and_(*conditions)
            query = query.where(combined)
            count_query = count_query.where(combined)
        query = (
            query.order_by(Hackathon.updated_at.desc(), Hackathon.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        async with async_session_factory() as session:
            rows_result = await session.execute(query)
            count_result = await session.execute(count_query)
            rows = rows_result.scalars().all()
            total = count_result.scalar() or 0
        return [_admin_hackathon_dict(row) for row in rows], total

    @staticmethod
    async def get_hackathon(hackathon_id: int) -> dict:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon).where(Hackathon.id == hackathon_id)
            )
            hackathon = result.scalar_one_or_none()
            if hackathon is None:
                raise AdminNotFoundError("赛事不存在")
            return _admin_hackathon_dict(hackathon)

    @staticmethod
    async def update_hackathon(hackathon_id: int, changes: dict) -> dict:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon).where(Hackathon.id == hackathon_id)
            )
            hackathon = result.scalar_one_or_none()
            if hackathon is None:
                raise AdminNotFoundError("赛事不存在")

            converted = dict(changes)
            if "status" in converted:
                converted["status"] = HackathonStatus(converted["status"])
            if "mode" in converted:
                converted["mode"] = HackathonMode(converted["mode"])
            if "display_status" in converted:
                converted["display_status"] = HackathonDisplayStatus(
                    converted["display_status"]
                )

            effective_registration_start = converted.get(
                "registration_start", hackathon.registration_start
            )
            effective_registration_end = converted.get(
                "registration_end", hackathon.registration_end
            )
            if (
                effective_registration_start is not None
                and effective_registration_end is not None
                and effective_registration_start > effective_registration_end
            ):
                raise AdminValidationError("报名开始时间不能晚于结束时间")

            effective_event_start = converted.get("event_start", hackathon.event_start)
            effective_event_end = converted.get("event_end", hackathon.event_end)
            if (
                effective_event_start is not None
                and effective_event_end is not None
                and effective_event_start > effective_event_end
            ):
                raise AdminValidationError("赛事开始时间不能晚于结束时间")

            for field_name, value in converted.items():
                setattr(hackathon, field_name, value)
            await session.commit()
            await session.refresh(hackathon)
            return _admin_hackathon_dict(hackathon)

    @staticmethod
    async def delete_hackathon(hackathon_id: int, confirm_name: str) -> dict:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon).where(Hackathon.id == hackathon_id)
            )
            hackathon = result.scalar_one_or_none()
            if hackathon is None:
                raise AdminNotFoundError("赛事不存在")
            if confirm_name != hackathon.name:
                raise AdminConflictError("赛事名称确认不匹配")
            deleted = {"id": hackathon.id, "name": hackathon.name}
            await session.delete(hackathon)
            await session.commit()
            return deleted


admin_service = AdminService()
