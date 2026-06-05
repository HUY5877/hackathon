"""
EDM 通知服务 — 对应架构图中的「EDM 通知服务 (B4)」
负责赛事上新通知的邮件推送
"""

from datetime import datetime

from app.services.auth_service import MOCK_USERS


class EDMService:
    """邮件通知服务（Mock 实现 — 不真实发送邮件）"""

    @staticmethod
    async def notify_new_hackathon(hackathon_data: dict) -> dict:
        """当新赛事录入时，匹配订阅用户并发送通知"""
        matched_users = []
        hackathon_tags = set(hackathon_data.get("track_tags") or [])
        hackathon_tech = set(hackathon_data.get("tech_tags") or [])

        for user in MOCK_USERS:
            if not user.get("edm_subscribed"):
                continue

            profile = user.get("profile_tags") or {}
            user_interests = set(profile.get("interests", []))
            user_tech = set(profile.get("tech_stack", []))

            # 标签匹配
            if hackathon_tags & user_interests or hackathon_tech & user_tech:
                matched_users.append(user["email"])

        # Mock: 记录日志而非实际发送
        result = {
            "hackathon_id": hackathon_data.get("id"),
            "hackathon_name": hackathon_data.get("name"),
            "matched_subscribers": len(matched_users),
            "recipients": matched_users[:5],  # 只展示前 5 个
            "sent_at": datetime.now().isoformat(),
            "status": "mock_sent",
        }

        return result

    @staticmethod
    async def send_custom_notification(user_id: int, subject: str, content: str) -> dict:
        """发送自定义通知给特定用户"""
        user = None
        for u in MOCK_USERS:
            if u["id"] == user_id:
                user = u
                break

        if not user or not user.get("edm_subscribed"):
            return {"status": "skipped", "reason": "user not subscribed"}

        return {
            "user_id": user_id,
            "email": user["email"],
            "subject": subject,
            "status": "mock_sent",
            "sent_at": datetime.now().isoformat(),
        }

    @staticmethod
    async def subscribe(user_id: int, subscribed: bool) -> bool:
        """更新用户 EDM 订阅状态"""
        for user in MOCK_USERS:
            if user["id"] == user_id:
                user["edm_subscribed"] = subscribed
                return True
        return False


edm_service = EDMService()