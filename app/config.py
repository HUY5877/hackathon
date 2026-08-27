"""
应用配置中心
基于 pydantic-settings 的环境变量管理
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，自动从 .env 文件和环境变量加载"""

    # ── 应用基础 ──────────────────────────────
    APP_NAME: str = "黑客松信息聚合平台"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # ── 服务端口 ──────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── 数据库 ────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:123456@localhost:5432/hackathon"
    DATABASE_URL_SYNC: str = "postgresql://postgres:123456@localhost:5432/hackathon"

    # ── Redis（缓存 & Celery） ────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT 认证 ──────────────────────────────
    JWT_SECRET_KEY: str = "change-me-to-a-secure-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # ── LLM API（AI 数据清洗） ────────────────
    LLM_API_KEY: str = ""
    LLM_API_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_SCREENING_API_BASE_URL: str = "https://api.stepfun.com/step_plan"
    LLM_SCREENING_MODEL: str = "step-explore"
    LLM_SCREENING_WORKERS: int = 2
    LLM_SCREENING_BATCH_SIZE: int = 100
    LLM_SCREENING_SCAN_INTERVAL_SECONDS: int = 300

    # ── 邮件服务（EDM） ───────────────────────
    SMTP_HOST: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "noreply@example.com"
    SMTP_PASSWORD: str = ""

    # ── 爬虫配置 ──────────────────────────────────────
    CRAWLER_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
    CRAWLER_REQUEST_DELAY: float = 2.0  # 请求间隔（秒）
    CRAWLER_PROXY_POOL: str = ""  # 代理地址，逗号分隔
    CRAWLER_TIMEOUT: float = 30.0  # 单请求超时（秒）
    CRAWLER_MAX_RETRIES: int = 3  # 最大重试次数
    CRAWLER_MAX_ITEMS_PER_PLATFORM: int = 0  # 每平台抓取上限（0=不限）
    CRAWLER_UA_ROTATION: bool = False  # 是否启用 UA 轮换
    CRAWLER_LLM_CACHE_TTL: int = 86400  # LLM 清洗结果缓存秒数
    CRAWLER_OUTPUT_DIR: str = "crawl_output"  # 爬取结果输出目录

    # ── 跨域 ──────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _load_settings() -> Settings:
    """加载配置，.env 优先"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        # pydantic_settings 会自动处理环境变量
        return Settings(_env_file=str(env_path))
    return Settings()


try:
    settings = _load_settings()
    # 打印加载结果（隐藏密码）
    db = settings.DATABASE_URL
    if "@" in db:
        db = db.split("@")[0].split("://")[0] + "://***@" + db.split("@")[1]
    print(f"📦 配置加载成功 | 数据库: {db}")
except Exception as e:
    print(f"⚠️  配置加载失败: {e}")
    settings = Settings()
