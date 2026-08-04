# Vercel 先监听端口再同步数据库设计

## 目标

Vercel 容器必须在 15 秒内监听 `$PORT`。启动流程调整为先启动 Uvicorn，再在后台依次执行模型差异生成和数据库升级，避免远程 PostgreSQL 延迟触发容器启动超时。

## 启动流程

1. `entrypoint.vercel.sh` 删除旧的就绪标记。
2. 后台启动 `vercel_migrations.py`。
3. 主进程立即 `exec uvicorn app.main:app` 并监听 `$PORT`。
4. 后台迁移进程仍严格执行 `revision --autogenerate`，随后执行 `upgrade head`。
5. 两步都结束后，迁移进程原子地创建就绪标记。
6. 就绪标记出现前，应用让首批 HTTP 请求条件等待迁移完成，以保持 Vercel invocation 活跃；标记出现后正常处理请求。
7. 等待超过 60 秒仍未就绪时，应用返回 `503` 和 `Retry-After: 1`。

## 错误处理

- 缺失 revision 错误沿用现有策略：记录警告并继续下一步。
- PostgreSQL 建连最长等待 5 秒；仅对 SQLAlchemy `OperationalError` 最多重试 3 次，避免单个 Vercel 实例永久卡在建连阶段。
- 其他 Alembic 错误保持非零退出，不创建就绪标记。
- 迁移失败后容器仍监听端口；请求等待超时后返回 `503`，避免未同步 Schema 接收业务流量。
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
- 自动化测试证明瞬时数据库连接错误会重试，非连接类错误仍直接失败。
- HTTP 测试证明首个请求会等到标记出现后返回 `200`，并在等待超时时返回 `503`。
- 推送 `dev-vercel` 后，Preview 冷启动日志应先出现 Uvicorn 监听，再出现两步迁移日志，最终 `/health` 返回 `200`。
