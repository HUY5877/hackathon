"""Administrator control-plane API."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_admin
from app.schemas.admin import AdminUserResponse
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.admin_service import (
    AdminConflictError,
    AdminNotFoundError,
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
