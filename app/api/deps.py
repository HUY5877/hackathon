"""API 依赖注入：认证、分页等公共依赖"""

from fastapi import Depends, Header, HTTPException

from app.services.auth_service import auth_service


async def get_current_user(authorization: str = Header(None)) -> dict:
    """从 Authorization Header 中解析当前登录用户"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = authorization.replace("Bearer ", "")
    user_id = await auth_service.decode_token(token)

    if user_id is None:
        raise HTTPException(status_code=401, detail="认证令牌无效或已过期")

    user = await auth_service.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")

    return user


async def get_optional_user(authorization: str = Header(None)) -> dict | None:
    """可选认证：已登录返回用户对象，未登录返回 None"""
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.replace("Bearer ", "")
    user_id = await auth_service.decode_token(token)

    if user_id is None:
        return None

    return await auth_service.get_user_by_id(user_id)