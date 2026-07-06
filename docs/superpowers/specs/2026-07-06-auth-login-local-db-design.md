# 登录后端接本地 SQLite — 设计文档

**日期**: 2026-07-06
**范围**: 把 auth（认证）链路从 mock 实现改为真实实现，接本地 SQLite 数据库，跑通「注册 → 登录 → 签发 JWT → 校验 token」全流程。
**不在范围内**: hackathons / inspiration / recommendations / empowerment / users(画像) 等模块继续保持 mock，不动，零回归。

---

## 1. 背景与现状

后端仓库（`HUY5877/hackathon` @ `dev-hy`）为 FastAPI + SQLAlchemy 2.0(async) + Pydantic 分层架构。auth 链路的「壳」已完整，只差把 mock 换成真实现：

| 文件 | 现状 | 处置 |
|------|------|------|
| `app/api/v1/auth.py` | 路由已写（register/login），调用 `auth_service` | **不改**（service 自管 session，见下） |
| `app/services/auth_service.py` | 全 mock：假密码 `$2b$12$mock_`、假 token（base64 非 JWT）、内存 list 存用户 | **重写为真实现** |
| `app/core/security.py` | 不存在 | **新建**：密码哈希 + JWT 编解码 |
| `app/models/user.py` | User ORM 模型完整（email/username/hashed_password/role/profile_tags...） | **不改**，仅建表 |
| `app/schemas/user.py` | 请求/响应 schema 完整（含 `TokenResponse.token_type` 默认 bearer） | **不改** |
| `app/api/deps.py` | `get_current_user`/`get_optional_user` 调 mock decode + get_user_by_id | **不改签名**，因其调用的 service 方法变真即可 |
| `app/middleware/auth_middleware.py` | 实质为放行占位 | **不改** |
| `app/db/session.py` | 异步引擎 + `async_session_factory` + `get_db` + `Base` | **不改** |
| `app/config.py` | 配置指向 Postgres | 仅通过 `.env` 覆盖为 SQLite |
| `requirements.txt` | 无 `aiosqlite` | **新增 aiosqlite** |

### 关键的现有范式（必须对齐）
`app/services/hackathon_service.py` 已给出真实 DB 实现的既定写法：**在 service 方法内部直接用 `async with async_session_factory() as session:` 自管会话**，而不是从路由 `Depends(get_db)` 注入。

→ **决策**：auth_service 沿用同一范式（service 自管 session）。好处是路由 `auth.py`、依赖 `deps.py` 的签名完全不用改，改动最小、风格统一。

---

## 2. 本地数据库选型：SQLite

- 驱动：`aiosqlite`（异步）。
- `.env` 本地配置：
  ```
  DATABASE_URL=sqlite+aiosqlite:///./hackathon.db
  DEBUG=true
  JWT_SECRET_KEY=<本地随机串>
  ```
- 生产 Postgres 配置保留在 `.env.example`，代码零改动可切回（SQLAlchemy 抹平方言差异）。

### 建表策略：只建 `users` 一张表
`hackathon` / `inspiration` / `empowerment` 三个模型使用 Postgres 专有的 `ARRAY(String)` 列，SQLite 不支持——因此**不能用 `Base.metadata.create_all`**（会因这些表建表失败而崩）。

→ **决策**：在 `main.py` 的 lifespan 启动钩子里，**只建 User 表**：
```python
async with engine.begin() as conn:
    await conn.run_sync(User.__table__.create, checkfirst=True)
```
`checkfirst=True` 保证已存在时不报错。本地测试要的是开箱即跑，不引入 alembic 迁移。生产以后再上 alembic。

---

## 3. 组件设计

### 3.1 新建 `app/core/security.py`（加解密单一职责）
纯函数，不碰数据库，独立可测：
- `hash_password(plain: str) -> str` — passlib bcrypt 哈希。
- `verify_password(plain: str, hashed: str) -> bool` — passlib 校验。
- `create_access_token(user_id: int) -> str` — python-jose 签 HS256 真 JWT，payload `{sub, exp, iat}`，用 `settings.JWT_SECRET_KEY` / `JWT_ALGORITHM` / `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`。
- `decode_access_token(token: str) -> int | None` — jose 解码 + 过期校验，返回 user_id，无效/过期返回 None。

**bcrypt 兼容提醒**：`passlib[bcrypt]` 与新版 `bcrypt>=4.1` 有已知的启动告警/报错（`bcrypt: no version info` / `AttributeError: __about__`）。实现时锁 `bcrypt<4.1`（或等价兼容处理），避免启动报错。

### 3.2 重写 `app/services/auth_service.py`（真实业务）
保持类 + 单例 `auth_service` 的现有形态；方法签名对上层保持兼容（返回 `dict | None`，因为路由用 `user["id"]` 下标访问）。内部用 `async_session_factory()` 自管 session。

- `async register(email, username, password) -> dict | None`
  - 查重：按 email 或 username 查，命中则返回 `None`（路由转 409）。
  - `hash_password(password)` → 构造 `User` → `session.add` → `commit` → `refresh`。
  - 返回 user 的 dict（含 id/email/username/role/profile_tags/edm_subscribed/email_verified/created_at）。
- `async login(email, password) -> dict | None`
  - 按 email 查用户；不存在或 `verify_password` 失败 → `None`（路由转 401）。
  - 成功返回 user dict。
- `async get_user_by_id(user_id) -> dict | None` — 真 DB 查询，返回 dict。
- `create_access_token(user_id) -> str` — 委托 `security.create_access_token`。
- `async decode_token(token) -> int | None` — 委托 `security.decode_access_token`。

ORM → dict 用一个内部小 helper（`_to_dict(user)`）统一，保证字段与 `UserProfileResponse` 对齐。

### 3.3 路由 / 依赖 / schema
- `auth.py`：**不改**。现有 `register`/`login` 已正确调用上述方法并组装 `ApiResponse[TokenResponse]`。
- `deps.py`：**不改**。`get_current_user` 已走 `decode_token` + `get_user_by_id`，二者变真即可。
- `schemas/user.py`：**不改**（`TokenResponse` 已含 `token_type="bearer"`）。

---

## 4. 数据流（登录成功路径）

```
POST /api/v1/auth/login {email, password}
  → auth.py:login()
    → auth_service.login(email, password)
        async_session_factory(): SELECT users WHERE email=? 
        → security.verify_password(password, user.hashed_password)  ✔
        → 返回 user dict
    → auth_service.create_access_token(user["id"])
        → security.create_access_token → jose HS256 JWT
    → ApiResponse(data=TokenResponse(access_token, user=UserProfileResponse))
  ← 200 {code, data:{access_token, token_type:"bearer", user:{...}}}

后续鉴权请求: Authorization: Bearer <token>
  → deps.get_current_user → security.decode_access_token → user_id
  → auth_service.get_user_by_id → user dict
```

---

## 5. 错误处理

| 场景 | 行为 |
|------|------|
| 注册 email/username 重复 | service 返回 None → 路由 `HTTPException(409, "邮箱或用户名已被注册")` |
| 登录 email 不存在 / 密码错误 | service 返回 None → 路由 `HTTPException(401, "邮箱或密码错误")`（不区分二者，防枚举） |
| token 缺失 / 格式错 | `deps` → `HTTPException(401, "未提供认证令牌")` |
| token 无效 / 过期 | `security.decode_access_token` 返回 None → `HTTPException(401, "认证令牌无效或已过期")` |
| 用户不存在（token 合法但用户被删） | `HTTPException(401, "用户不存在")` |

DB 写入异常沿用 `get_db` / `async_session_factory` 的 `rollback` 语义（service 内 `async with` 块出错自动回滚）。

---

## 6. 测试

### 单元/集成测试 `tests/test_auth.py`
用 `TestClient`（沿用 `conftest.py` 已有 `client` fixture），针对**独立临时 SQLite**（避免污染开发库 `hackathon.db`）：
- conftest 在 app 导入前，将 `DATABASE_URL` 环境变量设为临时 sqlite 文件，并建 User 表；测试结束清理。
- 覆盖用例：
  1. 注册成功 → 200，返回 access_token + user。
  2. 重复注册（同 email） → 409。
  3. 登录成功 → 200，token 可用。
  4. 密码错误 → 401。
  5. 用注册拿到的 token 访问受保护接口（如 `/api/v1/users/me`）→ 200 / 或校验 `get_current_user` 通过。
  6. 无效 token → 401。

### 手动冒烟
```
uvicorn app.main:app --reload
# 打开 http://localhost:8000/docs
# 依次点 POST /api/v1/auth/register → /api/v1/auth/login → 复制 token → Authorize → 访问受保护接口
```

---

## 7. 交付清单

- [ ] `requirements.txt` 加 `aiosqlite`（并处理 bcrypt 版本约束）
- [ ] `.env` 本地 SQLite 配置（不提交，`.env.example` 保留 Postgres）
- [ ] 新建 `app/core/__init__.py` + `app/core/security.py`
- [ ] 重写 `app/services/auth_service.py`
- [ ] `app/main.py` lifespan 内建 User 表
- [ ] `tests/test_auth.py`
- [ ] 本地跑通：pytest 全绿 + `/docs` 冒烟登录成功

---

## 8. 关键取舍备忘

1. **service 自管 session**（对齐 hackathon_service），非 Depends 注入 → 路由/deps 零改动。
2. **只建 users 表**（绕开其他模型的 Postgres ARRAY，SQLite 不兼容）。
3. **security 与 service 分层**：加解密独立成模块，边界清晰、易测。
4. **返回 dict 而非 ORM**：匹配现有路由 `user["id"]` 下标访问，最小改动。
5. 只碰 auth 链 + db 配置，其余模块 mock 不动 → 零回归。
