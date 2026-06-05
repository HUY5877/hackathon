"""
开发者赋能 API — Vibecoding 教程 / 参赛指南
对应架构图：内容调度服务 (B2) — 赋能区部分
对应 PRD 模块三：开发者赋能与 Vibecoding 专区
"""

from fastapi import APIRouter, HTTPException, Query

from app.schemas.empowerment import (
    EmpowermentFilterParams,
    EmpowermentArticleResponse,
)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services import empowerment_service

router = APIRouter(prefix="/empowerment", tags=["开发者赋能"])


@router.get("/vibecoding", response_model=ApiResponse[list[EmpowermentArticleResponse]])
async def get_vibecoding_articles(limit: int = Query(5, ge=1, le=20)):
    """获取 Vibecoding 教程列表"""
    items = await empowerment_service.get_vibecoding_articles(limit=limit)
    return ApiResponse(data=[EmpowermentArticleResponse.model_validate(a) for a in items])


@router.get("/guides", response_model=ApiResponse[list[EmpowermentArticleResponse]])
async def get_guide_articles(limit: int = Query(5, ge=1, le=20)):
    """获取参赛指南列表"""
    items = await empowerment_service.get_guide_articles(limit=limit)
    return ApiResponse(data=[EmpowermentArticleResponse.model_validate(a) for a in items])


@router.get("/articles", response_model=ApiResponse[PaginatedResponse[EmpowermentArticleResponse]])
async def list_articles(
    content_type: str | None = Query(None, description="内容类型: vibecoding/guide"),
    sub_category: str | None = Query(None, description="子分类"),
    difficulty_level: str | None = Query(None, description="难度: beginner/intermediate/advanced"),
    tags: str | None = Query(None, description="标签，逗号分隔"),
    keyword: str | None = Query(None, description="关键词搜索"),
    sort_by: str = Query("created_at", description="排序: created_at/view_count/like_count"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取赋能文章列表（支持筛选）"""
    tag_list = tags.split(",") if tags else None

    items, total = await empowerment_service.list_articles(
        content_type=content_type,
        sub_category=sub_category,
        difficulty_level=difficulty_level,
        tags=tag_list,
        keyword=keyword,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

    return ApiResponse(
        data=PaginatedResponse.from_data(
            items=[EmpowermentArticleResponse.model_validate(a) for a in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/articles/{slug}", response_model=ApiResponse[EmpowermentArticleResponse])
async def get_article_detail(slug: str):
    """获取赋能文章详情"""
    article = await empowerment_service.get_article(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    return ApiResponse(data=EmpowermentArticleResponse.model_validate(article))