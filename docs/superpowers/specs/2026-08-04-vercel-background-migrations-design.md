# Vercel 先监听端口再同步数据库设计

## 目标

Vercel 容器必须在 15 秒内监听 `$PORT`。启动流程调整为先启动 Uvicorn，再在后台依次执行模型差异生成和数据库升级，避免远程 PostgreSQL 延迟触发容器启动超时。

## 启动流程

1. `entrypoint.vercel.sh` 删除旧的就绪标记。
2. 后台启动 `vercel_migrations.py`。
3. 主进程立即 `exec uvicorn app.main:app` 并监听 `$PORT`。
4. 后台迁移进程仍严格执行 `revision --autogenerate`，随后执行 `upgrade head`。
5. 两步都结束后，迁移进程原子地创建就绪标记。
6. 就绪标记出现前，应用对 HTTP 请求返回 `503` 和 `Retry-After: 1`；出现后正常处理请求。

## 错误处理

- 缺失 revision 错误沿用现有策略：记录警告并继续下一步。
- 其他 Alembic 错误保持非零退出，不创建就绪标记。
- 迁移失败后容器仍监听端口，但所有请求保持 `503`，避免未同步 Schema 接收业务流量。
- 每个新容器启动时都先删除就绪标记，避免复用错误状态。

## 范围

- 仅修改 Vercel 入口、Vercel 迁移编排、应用就绪门禁及对应测试。
- 普通 `entrypoint.sh` 和 Docker Compose 启动顺序保持不变。
- 不修改 models、Alembic 配置、数据库版本指针或现有迁移文件。
- 不提交工作区已有的未跟踪 `alembic/versions/*.py` 文件。

## 验证

- 自动化测试证明 Uvicorn 在迁移进程结束前启动。
- 自动化测试证明迁移步骤仍为 `revision --autogenerate` 后接 `upgrade head`。
- 自动化测试证明迁移成功才创建就绪标记，其他错误不创建。
- HTTP 测试证明标记前返回 `503`，标记后 `/health` 返回 `200`。
- 推送 `dev-vercel` 后，Preview 冷启动日志应先出现 Uvicorn 监听，再出现两步迁移日志，最终 `/health` 返回 `200`。
