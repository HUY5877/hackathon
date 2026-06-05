"""
灵感池 API — 案例列表 / 公开摘要 / 完整详情（注册墙拦截）
对应架构图：内容调度服务 (B2) — 灵感池部分
对应 PRD 模块一：专属「灵感池」内容库
"""

from fastapi import APIRouter, HTTPException, Query, Depends

from app.schemas.inspiration import (
    InspirationFilterParams,
    InspirationSummaryResponse,
    InspirationDetailResponse,
    InteractionRequest,
)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services import inspiration_service
from app.api.deps import get_current_user, get_optional_user

router = APIRouter(prefix="/inspiration", tags=["灵感池"])


@router.get("", response_model=ApiResponse[PaginatedResponse[InspirationSummaryResponse]])
async def list_inspiration_items(
    category_tags: str | None = Query(None, description="分类标签，逗号分隔"),
    tech_tags: str | None = Query(None, description="技术栈标签，逗号分隔"),
    difficulty_level: str | None = Query(None, description="难度: beginner/intermediate/advanced"),
    keyword: str | None = Query(None, description="关键词搜索"),
    sort_by: str = Query("created_at", description="排序: created_at/like_count/view_count"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取灵感池内容列表（公开摘要，游客可见）"""
    cat_list = category_tags.split(",") if category_tags else None
    tech_list = tech_tags.split(",") if tech_tags else None

    items, total = await inspiration_service.list_items(
        category_tags=cat_list,
        tech_tags=tech_list,
        difficulty_level=difficulty_level,
        keyword=keyword,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

    return ApiResponse(
        data=PaginatedResponse.from_data(
            items=[InspirationSummaryResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{slug}", response_model=ApiResponse[InspirationDetailResponse])
async def get_inspiration_detail(
    slug: str,
    current_user: dict | None = Depends(get_optional_user),
):
    """
    获取灵感内容详情

    注册墙机制（对应 PRD 模块一）：
    - 游客（未登录）：仅返回公开摘要，full_content 等核心字段为 null
    - 已登录用户：返回完整内容
    """
    if current_user is None:
        # 游客 → 仅返回公开摘要
        item = await inspiration_service.get_public_summary(slug)
        if item is None:
            raise HTTPException(status_code=404, detail="内容不存在")
        return ApiResponse(
            code=403,
            message="请注册/登录后查看完整灵感内容",
            data=InspirationDetailResponse.model_validate(item),
        )
    else:
        # 已登录 → 返回完整内容
        item = await inspiration_service.get_item(slug)
        if item is None:
            raise HTTPException(status_code=404, detail="内容不存在")
        return ApiResponse(data=InspirationDetailResponse.model_validate(item))


@router.post("/interact", response_model=ApiResponse[dict])
async def record_interaction(
    req: InteractionRequest,
    current_user: dict = Depends(get_current_user),
):
    """记录用户交互（点赞 / 收藏）"""
    if req.interaction_type not in ("like", "bookmark"):
        raise HTTPException(status_code=400, detail="交互类型仅支持 like 或 bookmark")

    result = await inspiration_service.record_interaction(
        user_id=current_user["id"],
        item_id=req.item_id,
        interaction_type=req.interaction_type,
    )
    return ApiResponse(data=result, message=f"{'点赞' if req.interaction_type == 'like' else '收藏'}成功")