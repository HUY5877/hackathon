"""API v1 路由聚合"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.hackathons import router as hackathons_router
from app.api.v1.inspiration import router as inspiration_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.empowerment import router as empowerment_router
from app.api.v1.users import router as users_router
from app.api.v1.crawler import router as crawler_router

router = APIRouter(prefix="/api/v1")

router.include_router(auth_router)
router.include_router(hackathons_router)
router.include_router(inspiration_router)
router.include_router(recommendations_router)
router.include_router(empowerment_router)
router.include_router(users_router)
router.include_router(crawler_router)