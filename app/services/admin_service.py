"""Database-backed administrator operations."""

from sqlalchemy import func, or_, select

from app.db.session import async_session_factory
from app.models.user import User, UserRole


class AdminNotFoundError(LookupError):
    """Raised when an administrator target does not exist."""


class AdminConflictError(ValueError):
    """Raised when an administrator action conflicts with current state."""


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


admin_service = AdminService()
