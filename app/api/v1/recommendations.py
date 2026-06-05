"""
推荐 API — 综合热度榜 / 个性化推荐
对应架构图：推荐引擎服务 (B3)
对应 PRD 模块二：用户画像与精准触达系统
"""

from fastapi import APIRouter, Query, Depends

from app.schemas.hackathon import HackathonSummaryResponse
from app.schemas.common import ApiResponse
from app.services import recommendation_service
from app.api.deps import get_current_user, get_optional_user

router = APIRouter(prefix="/recommendations", tags=["推荐"])


@router.get("/hot", response_model=ApiResponse[list[HackathonSummaryResponse]])
async def get_hot_rankings(limit: int = Query(10, ge=1, le=50)):
    """全站综合热度榜单"""
    items = await recommendation_service.get_hot_rankings(limit=limit)
    return ApiResponse(data=[HackathonSummaryResponse.model_validate(h) for h in items])


@router.get("/for-you", response_model=ApiResponse[list[HackathonSummaryResponse]])
async def get_personalized_recommendations(
    limit: int = Query(5, ge=1, le=20),
    current_user: dict | None = Depends(get_optional_user),
):
    """
    「猜你适合」个性化推荐

    - 已登录且有画像标签：基于标签匹配推荐
    - 未登录或无画像：返回热门赛事
    """
    user_id = current_user["id"] if current_user else 0
    items = await recommendation_service.get_personalized_recommendations(
        user_id=user_id, limit=limit
    )
    return ApiResponse(data=[HackathonSummaryResponse.model_validate(h) for h in items])