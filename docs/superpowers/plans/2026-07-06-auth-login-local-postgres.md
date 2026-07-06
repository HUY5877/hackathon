# 登录后端接本地 PostgreSQL — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 auth 认证链从 mock 改为真实实现，接本地独立 PostgreSQL，跑通 注册 → 登录 → 签发 JWT → 校验 token。

**Architecture:** 新增 `app/core/security.py` 承担密码哈希 + JWT 编解码（纯函数、不碰 DB）；重写 `app/services/auth_service.py` 用真实 DB（对齐 `hackathon_service` 的 `async_session_factory()` 自管 session 范式），路由/依赖签名不变；`main.py` 启动时建 `users` 表。

**Tech Stack:** FastAPI 0.115 / SQLAlchemy 2.0 async / asyncpg / PostgreSQL 16 / passlib[bcrypt] / python-jose / pytest + httpx(TestClient)。

## Global Constraints

- 只改本地，**绝不 push 到 GitHub**；不往仓库加基础设施文件（Docker 用 `docker run`，已起容器 `hackthon-pg`）。
- 本地库 `hackathon`（`localhost:5432`，postgres/postgres）与线上完全隔离，不碰线上库。
- `.env` 已存在且被 gitignore，连接串已配好，**不提交 .env**。
- `bcrypt` 必须锁 `<4.1`，否则 passlib 1.7.4 启动报 `AttributeError: __about__`。
- 只碰 auth 链，其他模块保持 mock 不动（零回归）。
- 提交信息结尾加：`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`（仅本地 commit，不 push）。

---

### Task 1: 本地环境与依赖就绪

**Files:**
- Modify: `requirements.txt`（加 bcrypt 版本锁 + pytest）

**Interfaces:**
- Consumes: 无
- Produces: 可用的 Python 虚拟环境，装好所有依赖；本地 Postgres 可连。

- [ ] **Step 1: 确认本地 Postgres 可连**

Run:
```bash
docker exec -e PGPASSWORD=postgres hackthon-pg psql -U postgres -d hackathon -tAc "select 1;"
```
Expected: 输出 `1`。若容器没起：`docker start hackthon-pg`。

- [ ] **Step 2: 在 requirements.txt 锁 bcrypt 并加 pytest**

在 `requirements.txt` 里，`passlib[bcrypt]==1.7.4` 那一行下面新增一行，并在文件末尾加 pytest：
```
passlib[bcrypt]==1.7.4
bcrypt==4.0.1
```
文件末尾追加：
```
pytest==8.3.3
```

- [ ] **Step 3: 创建并激活虚拟环境，安装依赖**

Run（Windows PowerShell 或 Git Bash 均可，路径 `C:\Users\ASUS.LAPTOP-2OCDOG87\hackthon`）：
```bash
cd /c/Users/ASUS.LAPTOP-2OCDOG87/hackthon
python -m venv .venv
source .venv/Scripts/activate   # PowerShell 用: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Expected: 安装成功，无报错。`.venv/` 已在 .gitignore（若不在，本任务不提交它）。

- [ ] **Step 4: 冒烟——确认 app 能 import、能连库**

Run:
```bash
python -c "import app.main; print('import ok')"
```
Expected: 打印「📦 配置加载成功 | 数据库: postgresql+asyncpg://***@localhost:5432/hackathon」和「import ok」，无异常。

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore(auth): 锁 bcrypt<4.1 并加 pytest 依赖

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `app/core/security.py` 加解密模块

**Files:**
- Create: `app/core/__init__.py`
- Create: `app/core/security.py`
- Test: `tests/test_security.py`

**Interfaces:**
- Consumes: `app.config.settings`（JWT_SECRET_KEY / JWT_ALGORITHM / JWT_ACCESS_TOKEN_EXPIRE_MINUTES）
- Produces:
  - `hash_password(plain: str) -> str`
  - `verify_password(plain: str, hashed: str) -> bool`
  - `create_access_token(user_id: int) -> str`
  - `decode_access_token(token: str) -> int | None`

- [ ] **Step 1: 写失败测试 `tests/test_security.py`**

```python
"""app/core/security.py 单元测试（纯函数，不依赖数据库）"""
from app.core import security


def test_hash_and_verify_password_roundtrip():
    hashed = security.hash_password("s3cret-pw")
    assert hashed != "s3cret-pw"          # 已哈希，不是明文
    assert security.verify_password("s3cret-pw", hashed) is True
    assert security.verify_password("wrong-pw", hashed) is False


def test_create_and_decode_access_token_roundtrip():
    token = security.create_access_token(42)
    assert isinstance(token, str) and token.count(".") == 2   # JWT 三段式
    assert security.decode_access_token(token) == 42


def test_decode_invalid_token_returns_none():
    assert security.decode_access_token("not-a-real-token") is None
    assert security.decode_access_token("mock_jwt_abc") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_security.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.core'`）。

- [ ] **Step 3: 建 `app/core/__init__.py`（空文件）**

创建空文件 `app/core/__init__.py`。

- [ ] **Step 4: 写 `app/core/security.py`**

```python
"""密码哈希与 JWT 令牌 — 认证的加解密单一职责，不依赖数据库。"""

from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """bcrypt 哈希明文密码。"""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    """签发 HS256 JWT，payload = {sub, exp, iat}。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """解码并校验 JWT（含过期校验），返回 user_id；无效/过期返回 None。"""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_security.py -v`
Expected: 3 passed。

- [ ] **Step 6: Commit**

```bash
git add app/core/__init__.py app/core/security.py tests/test_security.py
git commit -m "feat(auth): 新增 security 模块（bcrypt 哈希 + JWT 编解码）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 测试基础设施（conftest：测试库 + 会话 client + 清表）

**Files:**
- Modify: `tests/conftest.py`（整体重写）

**Interfaces:**
- Consumes: `app.main.app`；本地容器 `hackthon-pg`
- Produces:
  - `client` fixture（session 级 `TestClient`，指向测试库 `hackathon_test`）
  - autouse `_clean_users` fixture（每用例前 `TRUNCATE users RESTART IDENTITY`）

- [ ] **Step 1: 整体重写 `tests/conftest.py`**

```python
"""测试配置：独立测试库 hackathon_test + 会话级 TestClient + 每用例清表。

关键点：
- 必须在 import app 之前设置 DATABASE_URL 环境变量（覆盖 .env），
  因为 app.db.session 在 import 时就用 settings.DATABASE_URL 建了引擎。
- 建表/清表走 docker exec psql 子进程（同步、无事件循环），
  避免 asyncpg 引擎跨事件循环报「attached to a different loop」。
"""

import os
import subprocess

# ── 必须在任何 app.* 导入之前执行 ──────────────────────
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

    进入 `with TestClient(app)` 会触发 lifespan，其中会 checkfirst 建 users 表。
    """
    _ensure_test_db()
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_users(client):
    """每个用例前清空 users 表并重置自增 ID，保证用例独立、断言可预测。"""
    _docker_psql("hackathon_test", "TRUNCATE TABLE users RESTART IDENTITY CASCADE;")
    yield
```

- [ ] **Step 2: 跑一条冒烟确认基础设施可用**

先确保 Task 4 还没写；用一个临时冒烟命令验证 client 能起（health 检查）：
```bash
python -c "
from fastapi.testclient import TestClient
import tests.conftest as c
c._ensure_test_db()
from app.main import app
with TestClient(app) as cl:
    r = cl.get('/health')
    print(r.status_code, r.json())
"
```
Expected: `200 {'status': 'ok', ...}`，且启动日志出现「✅ 数据库连接成功」（指向 hackathon_test）。

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(auth): conftest 接测试库 hackathon_test + 会话 client + 清表

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: auth_service 真实实现 + 启动建表 + 端到端认证测试

**Files:**
- Modify: `app/services/auth_service.py`（整体重写）
- Modify: `app/main.py`（lifespan 内建 users 表）
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes:
  - `app.core.security`（Task 2）
  - `app.db.session.async_session_factory` / `engine` / `Base`
  - `app.models.user.User` / `UserRole`
  - `client` fixture（Task 3）
- Produces（供 `auth.py` / `deps.py` 现有代码调用，签名与 mock 版一致）：
  - `auth_service.register(email, username, password) -> dict | None`
  - `auth_service.login(email, password) -> dict | None`
  - `auth_service.get_user_by_id(user_id) -> dict | None`
  - `auth_service.create_access_token(user_id) -> str`
  - `auth_service.decode_token(token) -> int | None`（async）

- [ ] **Step 1: 写失败测试 `tests/test_auth.py`**

```python
"""认证链端到端测试：注册 / 登录 / JWT 校验（走真实本地 Postgres 测试库）。"""
from app.core import security

REG = {"email": "alice@example.com", "username": "alice", "password": "pw123456"}


def _register(client, **overrides):
    payload = {**REG, **overrides}
    return client.post("/api/v1/auth/register", json=payload)


def test_register_success_returns_token_and_user(client):
    r = _register(client)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == REG["email"]
    assert data["user"]["username"] == REG["username"]
    assert "hashed_password" not in data["user"]   # 不泄露密码


def test_register_duplicate_email_returns_409(client):
    _register(client)
    r = _register(client, username="alice2")        # 同 email 不同用户名
    assert r.status_code == 409


def test_login_success_returns_token(client):
    _register(client)
    r = client.post("/api/v1/auth/login",
                    json={"email": REG["email"], "password": REG["password"]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["access_token"]


def test_login_wrong_password_returns_401(client):
    _register(client)
    r = client.post("/api/v1/auth/login",
                    json={"email": REG["email"], "password": "wrong-pw"})
    assert r.status_code == 401


def test_login_nonexistent_email_returns_401(client):
    r = client.post("/api/v1/auth/login",
                    json={"email": "nobody@example.com", "password": "whatever"})
    assert r.status_code == 401


def test_issued_token_decodes_to_registered_user_id(client):
    data = _register(client).json()["data"]
    token, user_id = data["access_token"], data["user"]["id"]
    assert security.decode_access_token(token) == user_id


def test_invalid_token_decodes_to_none(client):
    assert security.decode_access_token("garbage.token.value") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL（当前 mock 版：注册重复不查 DB、密码不校验 → 多个断言失败，或 500）。

- [ ] **Step 3: 整体重写 `app/services/auth_service.py`**

```python
"""用户与认证服务 — 真实数据库实现。

对齐 hackathon_service 的既定范式：service 方法内部用
`async with async_session_factory()` 自管会话，路由/依赖无需注入 db。
"""

from sqlalchemy import select, or_

from app.db.session import async_session_factory
from app.models.user import User, UserRole
from app.core import security


def _to_dict(user: User) -> dict:
    """ORM User → dict，字段对齐 UserProfileResponse（含 hashed_password 供内部用）。"""
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "hashed_password": user.hashed_password,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "profile_tags": user.profile_tags,
        "edm_subscribed": user.edm_subscribed,
        "email_verified": user.email_verified,
        "created_at": user.created_at,
    }


class AuthService:
    """认证服务（数据库实现）。"""

    @staticmethod
    async def register(email: str, username: str, password: str) -> dict | None:
        """注册新用户；email 或 username 已存在返回 None。"""
        async with async_session_factory() as session:
            existing = await session.execute(
                select(User).where(or_(User.email == email, User.username == username))
            )
            if existing.scalar_one_or_none() is not None:
                return None
            user = User(
                email=email,
                username=username,
                hashed_password=security.hash_password(password),
                role=UserRole.DEVELOPER,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return _to_dict(user)

    @staticmethod
    async def login(email: str, password: str) -> dict | None:
        """按 email 查用户并校验密码；失败返回 None。"""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if user is None or not security.verify_password(password, user.hashed_password):
                return None
            return _to_dict(user)

    @staticmethod
    async def get_user_by_id(user_id: int) -> dict | None:
        """按 ID 查用户。"""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            return _to_dict(user) if user is not None else None

    @staticmethod
    def create_access_token(user_id: int) -> str:
        """签发 JWT（委托 security）。"""
        return security.create_access_token(user_id)

    @staticmethod
    async def decode_token(token: str) -> int | None:
        """解析 JWT 得 user_id（委托 security）。"""
        return security.decode_access_token(token)


auth_service = AuthService()
```

- [ ] **Step 4: 在 `app/main.py` lifespan 内建 users 表**

在 `lifespan` 函数里，现有「测试数据库连接」的 `try/except` 之后、启动日志之前，插入建表逻辑：

```python
    # ── 启动时：建 users 表（仅本任务范围，checkfirst 幂等）──
    try:
        from app.db.session import engine
        from app.models.user import User
        async with engine.begin() as conn:
            await conn.run_sync(User.__table__.create, checkfirst=True)
        print("✅ users 表已就绪")
    except Exception as e:
        print(f"❌ 建 users 表失败: {e}")
```

（放在 `except Exception as e: print(f"❌ 数据库连接失败: {e}")` 这一段之后。）

- [ ] **Step 5: 跑认证测试确认通过**

Run: `pytest tests/test_auth.py -v`
Expected: 7 passed。

- [ ] **Step 6: 跑全量测试确认零回归**

Run: `pytest -v`
Expected: `tests/test_security.py`（3）+ `tests/test_auth.py`（7）全 passed，无 error。

- [ ] **Step 7: Commit**

```bash
git add app/services/auth_service.py app/main.py tests/test_auth.py
git commit -m "feat(auth): 登录/注册接真实 Postgres + JWT，启动建 users 表

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 手动冒烟 + DBeaver 可见性验证

**Files:** 无（纯验证）

**Interfaces:**
- Consumes: 前面全部任务
- Produces: 人工确认登录闭环在真实服务上可用

- [ ] **Step 1: 启动服务**

Run:
```bash
cd /c/Users/ASUS.LAPTOP-2OCDOG87/hackthon
source .venv/Scripts/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Expected: 日志出现「✅ 数据库连接成功」「✅ users 表已就绪」。

- [ ] **Step 2: 在 /docs 走注册→登录**

浏览器打开 `http://localhost:8000/docs`：
1. `POST /api/v1/auth/register` 填 `{email, username, password}` → 期望 200，返回 `access_token` + `user`。
2. `POST /api/v1/auth/login` 用同样 email/password → 期望 200，返回 `access_token`。
3. 复制 token，点右上「Authorize」填 `Bearer <token>`（如需测受保护接口）。

- [ ] **Step 3: 在 DBeaver 看到数据**

DBeaver 连接 `hackathon` 库（注意：**开发库是 `hackathon`，测试用的是 `hackathon_test`**）→ 刷新 → `public` → 表 → 应看到 `users` 表，里面有刚注册的用户，`hashed_password` 是 bcrypt 串（`$2b$...`）而非明文。

- [ ] **Step 4: 记录验证结果**

确认以上全部通过。登录后端本地闭环完成。

---

## Self-Review

**Spec coverage：**
- security 模块（哈希+JWT）→ Task 2 ✅
- auth_service 真实化（register/login/get_user_by_id/create/decode）→ Task 4 ✅
- 建 users 表 → Task 4 Step 4 ✅
- 本地 Postgres 配置 → Task 1（.env 已就绪）✅
- bcrypt 版本锁 → Task 1 Step 2 ✅
- 测试（注册/重复/登录/密码错/不存在/token 往返/无效 token）→ Task 3+4 ✅
- 手动冒烟 + DBeaver 可见 → Task 5 ✅
- 路由/deps/schema 不改 → 计划未触碰这些文件 ✅

**Placeholder scan：** 无 TBD/TODO；每个代码步骤都是完整可运行代码。

**Type consistency：** service 五个方法签名在 Task 4 Interfaces 与实现一致；`security.*` 四个函数签名在 Task 2 定义、Task 4 调用一致；`_to_dict` 字段与 `UserProfileResponse` 对齐（`hashed_password` 仅内部，`UserProfileResponse` 不含该字段故不泄露，测试已断言）。

**已知范围外：** `/api/v1/users/me` 依赖仍为 mock 的 `user_service`，故 token 校验用 service 层往返验证而非 `/me` 端到端——符合「只碰 auth 链」的范围约束。
