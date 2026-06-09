"""
推荐引擎服务 — 对应架构图中的「推荐引擎服务 (B3)」
基于用户画像标签与赛事标签的匹配运算
"""

from app.services.auth_service import MOCK_USERS
from app.services.hackathon_service import hackathon_service


class RecommendationService:
    """推荐引擎（数据库实现）"""

    @staticmethod
    async def get_personalized_recommendations(user_id: int, limit: int = 5) -> list[dict]:
        """基于用户画像标签匹配推荐赛事 — 对应 PRD「猜你适合」版块"""
        user = None
        for u in MOCK_USERS:
            if u["id"] == user_id:
                user = u
                break

        if not user or not user.get("profile_tags"):
            # 无画像 → 返回热门赛事
            return await hackathon_service.get_hot_list(limit)

        profile = user["profile_tags"]
        user_interests = set(profile.get("interests", []))
        user_tech = set(profile.get("tech_stack", []))

        # 从数据库获取所有赛事
        all_hackathons, _ = await hackathon_service.list_hackathons(page=1, page_size=100)

        scored = []
        for h in all_hackathons:
            score = 0
            h_track = set(h.get("track_tags") or [])
            h_tech = set(h.get("tech_tags") or [])

            interest_match = user_interests & h_track
            score += len(interest_match) * 10

            tech_match = user_tech & h_tech
            score += len(tech_match) * 5

            if h["status"] == "registering":
                score += 3
            elif h["status"] == "upcoming":
                score += 2

            if score > 0:
                scored.append((score, h))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored[:limit]]

    @staticmethod
    async def get_hot_rankings(limit: int = 10) -> list[dict]:
        """全站综合热度榜单"""
        return await hackathon_service.get_hot_list(limit)


recommendation_service = RecommendationService()