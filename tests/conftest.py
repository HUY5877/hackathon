"""测试配置：独立测试库 hackathon_test + 会话级 TestClient + 每用例清表。

关键点：
- 必须在 import app 之前设置 DATABASE_URL 环境变量（覆盖 .env），
  因为 app.db.session 在 import 时就用 settings.DATABASE_URL 建了引擎。
- 建表走 TestClient 的 lifespan（checkfirst 建 users 表）；
  清表走 docker exec psql 子进程（同步、无事件循环），
  避免 asyncpg 引擎跨事件循环报「attached to a different loop」。
"""

import os
import subprocess

# ── 必须在任何 app.* 导入之前执行 ──────────────────────
os.environ["PYTHONUTF8"] = "1"
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/hackathon_test"
)
os.environ["DATABASE_URL_SYNC"] = (
    "postgresql://postgres:postgres@localhost:5432/hackathon_test"
)

import pytest
from fastapi.testclient import TestClient

PG_CONTAINER = "hackthon-pg"


def _docker_psql(db: str, sql: str) -> None:
    """在容器里对指定库执行一条 SQL（同步）。"""
    subprocess.run(
        [
            "docker", "exec", "-e", "PGPASSWORD=postgres", PG_CONTAINER,
            "psql", "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1", "-c", sql,
        ],
        check=True, capture_output=True, text=True,
    )


def _ensure_test_db() -> None:
    """创建测试库 hackathon_test（已存在则忽略错误）。"""
    subprocess.run(
        [
            "docker", "exec", "-e", "PGPASSWORD=postgres", PG_CONTAINER,
            "createdb", "-U", "postgres", "hackathon_test",
        ],
        capture_output=True, text=True,  # 不加 check：已存在时返回非 0，忽略
    )


@pytest.fixture(scope="session")
def client():
    """会话级 TestClient（单一事件循环，规避 asyncpg 跨循环问题）。

    进入 `with TestClient(app)` 会触发 lifespan，其中 checkfirst 建 users 表。
    """
    _ensure_test_db()
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _truncate(request):
    """每个「用到 client（即数据库）」的用例前清空 users 表并重置自增 ID。

    只对请求了 client 的测试生效，纯单元测试（如 test_security）不被牵连连库。
    """
    if "client" in request.fixturenames:
        _docker_psql("hackathon_test", "TRUNCATE TABLE users RESTART IDENTITY CASCADE;")
    yield
