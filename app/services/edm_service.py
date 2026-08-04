"""
EDM 通知服务 — 对应架构图中的「EDM 通知服务 (B4)」
负责赛事上新通知的邮件推送

真实数据库实现（订阅状态落库；邮件仍为 Mock 发送，不真实外发）。
"""

from datetime import datetime

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.user import User


class EDMService:
    """邮件通知服务（订阅状态走数据库；邮件发送仍为 Mock）"""

    @staticmethod
    async def notify_new_hackathon(hackathon_data: dict) -> dict:
        """当新赛事录入时，匹配订阅用户并发送通知"""
        hackathon_tags = set(hackathon_data.get("track_tags") or [])
        hackathon_tech = set(hackathon_data.get("tech_tags") or [])

        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.edm_subscribed.is_(True))
            )
            subscribers = result.scalars().all()

        matched_users = []
        for user in subscribers:
            profile = user.profile_tags or {}
            user_interests = set(profile.get("interests", []))
            user_tech = set(profile.get("tech_stack", []))
            if hackathon_tags & user_interests or hackathon_tech & user_tech:
                matched_users.append(user.email)

        # Mock: 记录日志而非实际发送
        return {
            "hackathon_id": hackathon_data.get("id"),
            "hackathon_name": hackathon_data.get("name"),
            "matched_subscribers": len(matched_users),
            "recipients": matched_users[:5],  # 只展示前 5 个
            "sent_at": datetime.now().isoformat(),
            "status": "mock_sent",
        }

    @staticmethod
    async def send_custom_notification(user_id: int, subject: str, content: str) -> dict:
        """发送自定义通知给特定用户"""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

        if user is None or not user.edm_subscribed:
            return {"status": "skipped", "reason": "user not subscribed"}

        return {
            "user_id": user_id,
            "email": user.email,
            "subject": subject,
            "status": "mock_sent",
            "sent_at": datetime.now().isoformat(),
        }

    @staticmethod
    async def subscribe(user_id: int, subscribed: bool) -> bool:
        """更新用户 EDM 订阅状态（落库）。用户不存在返回 False。"""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                return False
            user.edm_subscribed = subscribed
            await session.commit()
            return True


edm_service = EDMService()
