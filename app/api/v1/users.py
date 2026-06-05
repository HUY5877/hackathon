"""
用户 API — 画像管理 / EDM 订阅
对应架构图：用户与认证服务 (B1) + EDM 通知服务 (B4)
对应 PRD 模块二：用户画像与精准触达系统
"""

from fastapi import APIRouter, HTTPException, Depends

from app.schemas.user import (
    UserProfileResponse,
    UserProfileTagsUpdate,
    EDMSubscribeRequest,
)
from app.schemas.common import ApiResponse
from app.services import user_service, edm_service
from app.api.deps import get_current_user

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("/me", response_model=ApiResponse[UserProfileResponse])
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """获取当前用户画像"""
    profile = await user_service.get_profile(current_user["id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ApiResponse(data=UserProfileResponse.model_validate(profile))


@router.put("/me/tags", response_model=ApiResponse[UserProfileResponse])
async def update_profile_tags(
    req: UserProfileTagsUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    更新用户画像标签

    对应 PRD 模块二的「极简用户画像构建」：
    在注册后/首次登录时通过标签选择向导收集用户特征
    """
    updated = await user_service.update_profile_tags(
        user_id=current_user["id"],
        tags=req.model_dump(exclude_none=True),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ApiResponse(data=UserProfileResponse.model_validate(updated))


@router.put("/me/edm-subscribe", response_model=ApiResponse[dict])
async def toggle_edm_subscription(
    req: EDMSubscribeRequest,
    current_user: dict = Depends(get_current_user),
):
    """设置 EDM 邮件订阅状态 — 对应 PRD 模块二的「合规化邮件订阅」"""
    success = await edm_service.subscribe(current_user["id"], req.subscribed)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")

    return ApiResponse(
        message=f"邮件订阅已{'开启' if req.subscribed else '关闭'}",
        data={"subscribed": req.subscribed},
    )


@router.get("/me/bookmarks", response_model=ApiResponse[list])
async def get_my_bookmarks(current_user: dict = Depends(get_current_user)):
    """获取当前用户的收藏列表（Mock: 返回空列表）"""
    # TODO: 实际查询 user_interactions 表
    return ApiResponse(data=[], message="收藏列表（功能开发中）")