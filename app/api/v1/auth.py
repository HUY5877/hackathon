"""
认证 API — 注册 / 登录 / Token 刷新
对应架构图：用户与认证服务 (B1)
"""

from fastapi import APIRouter, HTTPException, Depends

from app.schemas.user import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserProfileResponse,
)
from app.schemas.common import ApiResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=ApiResponse[TokenResponse])
async def register(req: UserRegisterRequest):
    """用户注册"""
    user = await auth_service.register(
        email=req.email,
        username=req.username,
        password=req.password,
    )
    if user is None:
        raise HTTPException(status_code=409, detail="邮箱或用户名已被注册")

    token = auth_service.create_access_token(user["id"])
    return ApiResponse(
        data=TokenResponse(
            access_token=token,
            user=UserProfileResponse.model_validate(user),
        )
    )


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(req: UserLoginRequest):
    """用户登录"""
    user = await auth_service.login(req.email, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = auth_service.create_access_token(user["id"])
    return ApiResponse(
        data=TokenResponse(
            access_token=token,
            user=UserProfileResponse.model_validate(user),
        )
    )