"""
推荐引擎服务 — 对应架构图中的「推荐引擎服务 (B3)」
基于用户画像标签与赛事标签的匹配运算
"""

from app.services.auth_service import MOCK_USERS
from app.services.hackathon_service import MOCK_HACKATHONS


class RecommendationService:
    """推荐引擎（Mock 实现）"""

    @staticmethod
    async def get_personalized_recommendations(user_id: int, limit: int = 5) -> list[dict]:
        """基于用户画像标签匹配推荐赛事 — 对应 PRD「猜你适合」版块"""
        # 获取用户画像
        user = None
        for u in MOCK_USERS:
            if u["id"] == user_id:
                user = u
                break

        if not user or not user.get("profile_tags"):
            # 无画像 → 返回热门赛事
            return sorted(
                [dict(h) for h in MOCK_HACKATHONS],
                key=lambda h: h["view_count"],
                reverse=True,
            )[:limit]

        profile = user["profile_tags"]
        user_interests = set(profile.get("interests", []))
        user_tech = set(profile.get("tech_stack", []))

        scored = []
        for h in MOCK_HACKATHONS:
            score = 0
            h_track = set(h.get("track_tags") or [])
            h_tech = set(h.get("tech_tags") or [])

            # 兴趣标签匹配
            interest_match = user_interests & h_track
            score += len(interest_match) * 10

            # 技术栈匹配
            tech_match = user_tech & h_tech
            score += len(tech_match) * 5

            # 状态加分（正在进行中的赛事优先）
            if h["status"] == "registering":
                score += 3
            elif h["status"] == "upcoming":
                score += 2

            if score > 0:
                scored.append((score, dict(h)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored[:limit]]

    @staticmethod
    async def get_hot_rankings(limit: int = 10) -> list[dict]:
        """全站综合热度榜单"""
        return sorted(
            [dict(h) for h in MOCK_HACKATHONS],
            key=lambda h: h["view_count"],
            reverse=True,
        )[:limit]


recommendation_service = RecommendationService()