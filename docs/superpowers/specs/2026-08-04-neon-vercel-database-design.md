# Vercel Neon 数据库切换设计

## 目标

让 Vercel 部署优先使用已连接到项目的 Neon PostgreSQL，同时保留现有
`DATABASE_URL` 和 `DATABASE_URL_SYNC` 作为非 Vercel 环境及回退配置。
数据库迁移流程保持不变：启动后根据当前 models 自动生成差异迁移，再执行升级。

## 已确认的外部配置

- Vercel 项目：`sust-acmer/hackathon`
- Neon 资源：`hackathon-postgres`
- 方案：Free
- 区域：Singapore (`sin1`)
- 作用环境：Production、Preview
- Vercel 注入变量：`NEON_URL`
- Neon Auth：关闭

## 方案

新增一个无副作用的数据库 URL 解析模块，集中完成以下逻辑：

1. `NEON_URL` 存在时，应用和 Alembic 都从它派生连接地址。
2. 异步应用连接使用 `postgresql+asyncpg://`，并把 Neon URL 中面向 libpq 的
   TLS 查询参数转换为 asyncpg 可接受的形式。
3. Alembic 同步连接使用 `postgresql://`，保留 Neon 所需的同步驱动参数。
4. `NEON_URL` 不存在时，原样使用现有的 `DATABASE_URL` 和
   `DATABASE_URL_SYNC`，保证服务器 Docker Compose 配置不受影响。

配置加载和 Alembic 环境都调用同一个解析模块，避免两处转换规则漂移。现有迁移脚本、
迁移历史判断、自动生成差异和升级顺序均不修改。

## 备选方案与取舍

### 采用：应用兼容 `NEON_URL`

保留旧变量，切换可回退；Vercel 集成负责管理 Neon 凭据，不需要复制或显示密码。
代价是一处小型 URL 兼容逻辑。

### 不采用：删除旧变量并让集成占用 `DATABASE_URL`

代码改动较少，但会破坏当前服务器数据库的回退配置，而且 Neon 提供的同步 URL 不能
直接传给 SQLAlchemy asyncpg 引擎。

### 不采用：手工复制 Neon 密钥到两个现有变量

无需代码改动，但要复制敏感凭据，两个 URL 可能发生漂移，后续凭据轮换也无法自动同步。

## 数据流

Vercel 注入 `NEON_URL` 后，配置加载阶段派生异步 URL 给 FastAPI；Alembic 启动时由同一
模块派生同步 URL。迁移成功后写入现有就绪标记，请求处理中间件解除启动等待。

在服务器 Docker Compose 环境中没有 `NEON_URL`，因此继续使用原来的两个数据库变量，
行为不变。

## 错误处理

- 非 PostgreSQL 的 `NEON_URL` 在启动阶段给出明确配置错误，不静默连接错误数据库。
- URL 转换保留与驱动兼容的未知查询参数，只移除 asyncpg 明确不支持的参数。
- Neon 连接或迁移失败时继续沿用现有重试、日志与 `503 starting` 行为。

## 测试与验收

- 单元测试先覆盖 Neon 优先级、同步/异步 URL 转换和旧配置回退。
- 先确认测试在未实现时按预期失败，再实现最小代码使其通过。
- 运行完整 pytest 套件。
- 推送 `dev-vercel` 后重新部署 Production。
- 线上 `/health` 必须返回成功，并在 Vercel 日志中确认迁移连接不再访问
  `101.34.57.133:15432`。

## 范围外事项

- 不迁移腾讯云 PostgreSQL 中的已有业务数据。
- 不修改或删除现有 Alembic 版本文件。
- 不修改服务器 Docker Compose 数据库配置。
