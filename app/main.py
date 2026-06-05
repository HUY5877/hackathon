"""
FastAPI 应用入口 — 对应架构图中的「API 网关 (Gateway)」

启动方式:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

API 文档:
    Swagger UI:  http://localhost:8000/docs
    ReDoc:       http://localhost:8000/redoc

架构映射（前端 ↔ 后端）:
    F1 信息大厅     ↔ /api/v1/hackathons/*
    F2 专属灵感池   ↔ /api/v1/inspiration/*
    F3 个人推荐区   ↔ /api/v1/recommendations/*
    F4 开发者赋能区 ↔ /api/v1/empowerment/*
    用户与认证       ↔ /api/v1/auth/* + /api/v1/users/*
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.router import router as api_v1_router
from app.middleware.auth_middleware import AuthMiddleware
from app.crawler.scheduler import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ── 启动时 ──
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    print(f"📡 API 文档: http://{settings.HOST}:{settings.PORT}/docs")
    print(f"🔧 Debug 模式: {settings.DEBUG}")
    # TODO: 启动 APScheduler 定时爬虫任务
    # from apscheduler.schedulers.asyncio import AsyncIOScheduler
    # ...

    yield

    # ── 关闭时 ──
    print("🛑 应用关闭中...")
    # TODO: 关闭数据库连接池、取消定时任务等


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## 黑客松信息聚合与开发者赋能平台

### 核心模块
- **信息大厅**: 黑客松赛事列表、多维筛选、外链跳转
- **灵感池**: PGC 精选案例深度拆解、注册墙拦截
- **推荐**: 综合热度榜、「猜你适合」个性化推荐
- **开发者赋能**: Vibecoding 教程、黑客松参赛指南
- **用户系统**: 认证、画像标签、EDM 邮件订阅
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS 中间件 ───────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 认证中间件 ───────────────────────────
app.add_middleware(AuthMiddleware)

# ── 注册路由 ─────────────────────────────
app.include_router(api_v1_router)


# ── 健康检查 ──────────────────────────────

@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/", tags=["系统"])
async def root():
    """根路径重定向到 API 文档"""
    return {
        "message": f"欢迎使用 {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api": "/api/v1",
    }


@app.get("/api/crawler/status", tags=["系统"])
async def crawler_status():
    """爬虫系统状态查询"""
    return scheduler.get_status()


# ── 开发服务器入口 ─────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )