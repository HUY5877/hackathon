"""Administrator control-plane API."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_admin
from app.schemas.admin import (
    AdminCrawlerOverviewResponse,
    AdminCrawlerTaskCreate,
    AdminCrawlerTaskResponse,
    AdminHackathonDeleteRequest,
    AdminHackathonResponse,
    AdminHackathonUpdate,
    AdminUserResponse,
    DeletedResourceResponse,
)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.crawler.apscheduler_manager import scheduler_manager
from app.crawler.scheduler import CRAWLER_REGISTRY, CRAWL_SCHEDULE, scheduler
from app.crawler.task_manager import (
    CrawlerTaskConflict,
    CrawlerTaskNotFound,
    crawler_task_manager,
)
from app.services.admin_service import (
    AdminConflictError,
    AdminNotFoundError,
    AdminValidationError,
    admin_service,
)


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/admin",
    tags=["管理员"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "/users",
    response_model=ApiResponse[PaginatedResponse[AdminUserResponse]],
)
async def list_users(
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    items, total = await admin_service.list_users(
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(
        data=PaginatedResponse.from_data(
            items=[AdminUserResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/users/{user_id}/promote",
    response_model=ApiResponse[AdminUserResponse],
)
async def promote_user(
    user_id: int,
    current_admin: dict = Depends(require_admin),
):
    try:
        user = await admin_service.promote_user(user_id)
    except AdminNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AdminConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info(
        "Administrator promoted user",
        extra={
            "operation": "promote_user",
            "actor_id": current_admin["id"],
            "target_id": user_id,
        },
    )
    return ApiResponse(message="用户已设为管理员", data=AdminUserResponse.model_validate(user))


@router.get(
    "/hackathons",
    response_model=ApiResponse[PaginatedResponse[AdminHackathonResponse]],
)
async def list_hackathons(
    keyword: str | None = Query(default=None),
    source_platform: str | None = Query(default=None),
    status: Literal["upcoming", "registering", "ongoing", "ended"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    items, total = await admin_service.list_hackathons(
        keyword=keyword,
        source_platform=source_platform,
        status=status,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(
        data=PaginatedResponse.from_data(
            items=[AdminHackathonResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/hackathons/{hackathon_id}",
    response_model=ApiResponse[AdminHackathonResponse],
)
async def get_hackathon(hackathon_id: int):
    try:
        hackathon = await admin_service.get_hackathon(hackathon_id)
    except AdminNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=AdminHackathonResponse.model_validate(hackathon))


@router.post(
    "/hackathons/{hackathon_id}/update",
    response_model=ApiResponse[AdminHackathonResponse],
)
async def update_hackathon(
    hackathon_id: int,
    request: AdminHackathonUpdate,
    current_admin: dict = Depends(require_admin),
):
    try:
        hackathon = await admin_service.update_hackathon(
            hackathon_id,
            request.model_dump(exclude_unset=True),
        )
    except AdminNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AdminValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info(
        "Administrator updated hackathon",
        extra={
            "operation": "update_hackathon",
            "actor_id": current_admin["id"],
            "target_id": hackathon_id,
        },
    )
    return ApiResponse(message="赛事已更新", data=AdminHackathonResponse.model_validate(hackathon))


@router.post(
    "/hackathons/{hackathon_id}/delete",
    response_model=ApiResponse[DeletedResourceResponse],
)
async def delete_hackathon(
    hackathon_id: int,
    request: AdminHackathonDeleteRequest,
    current_admin: dict = Depends(require_admin),
):
    try:
        deleted = await admin_service.delete_hackathon(
            hackathon_id,
            request.confirm_name,
        )
    except AdminNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AdminConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info(
        "Administrator deleted hackathon",
        extra={
            "operation": "delete_hackathon",
            "actor_id": current_admin["id"],
            "target_id": hackathon_id,
        },
    )
    return ApiResponse(message="赛事已永久删除", data=DeletedResourceResponse.model_validate(deleted))


@router.get(
    "/crawler/overview",
    response_model=ApiResponse[AdminCrawlerOverviewResponse],
)
async def get_crawler_overview():
    """Return the live scheduler and crawler registry state."""

    return ApiResponse(
        data=AdminCrawlerOverviewResponse(
            platforms=list(CRAWLER_REGISTRY),
            schedules=dict(CRAWL_SCHEDULE),
            scheduler_running=scheduler_manager.is_running,
            jobs=scheduler_manager.get_jobs(),
            recent_runs=scheduler.get_history(limit=20),
        )
    )


@router.post(
    "/crawler/tasks",
    response_model=ApiResponse[AdminCrawlerTaskResponse],
    status_code=202,
)
async def create_crawler_task(
    request: AdminCrawlerTaskCreate,
    current_admin: dict = Depends(require_admin),
):
    """Accept a single-platform or full crawler run for background execution."""

    if request.scope == "platform" and request.platform not in CRAWLER_REGISTRY:
        raise HTTPException(status_code=404, detail=f"未知平台: {request.platform}")
    try:
        task = crawler_task_manager.create(
            scope=request.scope,
            platform=request.platform,
            actor_id=current_admin["id"],
        )
    except CrawlerTaskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    logger.info(
        "Administrator triggered crawler",
        extra={
            "operation": "trigger_crawler",
            "actor_id": current_admin["id"],
            "target_id": task.task_id,
            "target_platform": request.platform,
            "target_scope": request.scope,
        },
    )
    return ApiResponse(
        message="爬虫任务已启动",
        data=AdminCrawlerTaskResponse.model_validate(task),
    )


@router.get(
    "/crawler/tasks",
    response_model=ApiResponse[list[AdminCrawlerTaskResponse]],
)
async def list_crawler_tasks(
    status: Literal["queued", "running", "completed", "failed"] | None = Query(default=None),
):
    tasks = crawler_task_manager.list_tasks(status=status)
    return ApiResponse(
        data=[AdminCrawlerTaskResponse.model_validate(task) for task in tasks]
    )


@router.get(
    "/crawler/tasks/{task_id}",
    response_model=ApiResponse[AdminCrawlerTaskResponse],
)
async def get_crawler_task(task_id: str):
    try:
        task = crawler_task_manager.get_task(task_id)
    except CrawlerTaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=AdminCrawlerTaskResponse.model_validate(task))
