"""
信息大厅 API — 黑客松赛事列表 / 详情 / 筛选 / 外链跳转
对应架构图：内容调度服务 (B2) — 信息大厅部分
对应 PRD 模块四：黑客松基础信息大厅与自动化引擎
"""

from fastapi import APIRouter, HTTPException, Query, Depends

from app.schemas.hackathon import (
    HackathonFilterParams,
    HackathonSummaryResponse,
    HackathonDetailResponse,
    ExternalClickResponse,
)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services import hackathon_service
from app.api.deps import get_optional_user

router = APIRouter(prefix="/hackathons", tags=["信息大厅"])


@router.get("", response_model=ApiResponse[PaginatedResponse[HackathonSummaryResponse]])
async def list_hackathons(
    status: str | None = Query(None, description="赛事状态: upcoming/registering/ongoing/ended"),
    mode: str | None = Query(None, description="赛事形式: online/offline/hybrid"),
    track_tags: str | None = Query(None, description="赛道标签，逗号分隔"),
    tech_tags: str | None = Query(None, description="技术栈标签，逗号分隔"),
    country: str | None = Query(None, description="国家/地区"),
    keyword: str | None = Query(None, description="关键词搜索"),
    sort_by: str = Query("event_start", description="排序字段: event_start/prize_pool_usd/view_count/created_at"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取黑客松赛事列表（支持多维筛选）"""
    track_list = track_tags.split(",") if track_tags else None
    tech_list = tech_tags.split(",") if tech_tags else None

    items, total = await hackathon_service.list_hackathons(
        status=status,
        mode=mode,
        track_tags=track_list,
        tech_tags=tech_list,
        country=country,
        keyword=keyword,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

    return ApiResponse(
        data=PaginatedResponse.from_data(
            items=[HackathonSummaryResponse.model_validate(h) for h in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/hot", response_model=ApiResponse[list[HackathonSummaryResponse]])
async def get_hot_list(limit: int = Query(5, ge=1, le=20)):
    """获取综合热度榜单"""
    items = await hackathon_service.get_hot_list(limit=limit)
    return ApiResponse(data=[HackathonSummaryResponse.model_validate(h) for h in items])


@router.get("/{slug}", response_model=ApiResponse[HackathonDetailResponse])
async def get_hackathon_detail(slug: str):
    """获取黑客松赛事详情"""
    hackathon = await hackathon_service.get_hackathon(slug)
    if hackathon is None:
        raise HTTPException(status_code=404, detail="赛事不存在")
    return ApiResponse(data=HackathonDetailResponse.model_validate(hackathon))


@router.post("/{hackathon_id}/click", response_model=ApiResponse[ExternalClickResponse])
async def record_external_click(hackathon_id: int):
    """记录「去官网报名」外链点击 — 对应 PRD 模块四的转化追踪"""
    result = await hackathon_service.record_external_click(hackathon_id)
    return ApiResponse(
        data=ExternalClickResponse(
            click_id=result["click_id"],
            message="点击已记录，正在跳转至官方报名页面...",
        )
    )