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
from app.crawler.apscheduler_manager import scheduler_manager
from app.crawler.logging_config import setup_logging
from app.crawler.screening_worker import screening_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ── 启动时 ──
    # 配置日志（debug 模式下用 text，生产可用 json）
    log_format = "text" if settings.DEBUG else "json"
    setup_logging(level="DEBUG" if settings.DEBUG else "INFO", format_type=log_format)

    # ── 启动时：测试数据库连接 ──
    try:
        from app.db.session import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        print(f"✅ 数据库连接成功: {settings.DATABASE_URL}")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
    # 建表交给 alembic 迁移流水线（entrypoint.sh: autogenerate + upgrade），
    # users 表由 app/models/user.py 的 User 模型经 alembic env.py 自动扫描建立，
    # 这里不再手动 create_all，避免两套建表逻辑并存。
    # ── 启动日志 ──
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    print(f"📡 API 文档: http://{settings.HOST}:{settings.PORT}/docs")
    print(f"🔧 Debug 模式: {settings.DEBUG}")

    # 先启动异步质量筛选 worker，再启动爬虫和 pending 补扫定时任务。
    try:
        await screening_worker.start()
    except Exception as e:
        print(f"⚠️ 大模型筛选 worker 启动失败: {e}")
    try:
        await screening_worker.scan_pending()
    except Exception as e:
        print(f"⚠️ 未筛选赛事首次补扫失败: {e}")
    try:
        scheduler_manager.start()
        print(f"⏰ 定时爬虫已启动，共 {len(scheduler_manager.get_jobs())} 个任务")
    except Exception as e:
        print(f"⚠️ 定时爬虫启动失败: {e}")

    yield

    # ── 关闭时 ──
    print("🛑 应用关闭中...")
    scheduler_manager.stop()
    await screening_worker.stop()


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


@app.get("/api/crawler/status", tags=["系统"], deprecated=True)
async def crawler_status_legacy():
    """爬虫系统状态查询（已迁移至 /api/v1/crawler/status）"""
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
