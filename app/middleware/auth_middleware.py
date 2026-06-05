"""
认证中间件 — 在请求进入路由前验证 JWT Token
对应架构图：API 网关 (Gateway)
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.services.auth_service import auth_service

# 不需要认证的路径（白名单）
PUBLIC_PATHS = {
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/hackathons",
    "/api/v1/hackathons/hot",
    "/api/v1/inspiration",
    "/api/v1/empowerment",
    "/api/v1/recommendations/hot",
    "/api/v1/recommendations/for-you",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/health",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    JWT 认证中间件

    当前实现：仅在路由层通过 Depends 处理认证
    此中间件保留用于未来扩展（如全局限流、请求日志、CORS 等）
    """

    async def dispatch(self, request: Request, call_next):
        # 路径白名单放行
        path = request.url.path

        # 公共路径跳过认证
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        # 详情页 GET 请求放行
        if request.method == "GET":
            return await call_next(request)

        # 其他请求需要认证（由路由层 Depends 处理）
        return await call_next(request)