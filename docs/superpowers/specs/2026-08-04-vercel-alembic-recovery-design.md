# Vercel Alembic 缺失 Revision 恢复设计

## 目标

保持 Vercel 容器现有的迁移顺序：先升级已有迁移，再根据当前 SQLAlchemy models 自动生成差异文件，最后应用新迁移。同时允许数据库的 `alembic_version` 指向镜像中不存在的 revision 时破坏旧迁移历史并恢复启动。

## 启动流程

1. 执行 `alembic upgrade head`。
2. 若执行成功，直接进入原有的自动生成流程。
3. 若执行失败且输出包含 `Can't locate revision identified by`，执行 `alembic stamp head --purge`，清除数据库中无法解析的版本指针并按当前仓库迁移头重新标记。
4. 若失败原因不是缺失 revision，保留失败并退出容器，不掩盖连接、权限或迁移代码错误。
5. 执行 `alembic revision --autogenerate -m "auto"`。
6. 执行 `alembic upgrade head`。
7. 启动 Uvicorn。

## 修改范围

- 仅修改 `entrypoint.vercel.sh` 及其自动化测试。
- 不修改、删除或提交工作区现有的 `alembic/versions/*.py` 未跟踪文件。
- 不修改普通 Docker Compose 的服务配置。
- Vercel 环境变量和数据库连接保持当前配置。

## 错误与风险

该恢复会丢弃无法解析的 Alembic 历史指针，并假设数据库当前实际 Schema 可以作为重新计算差异的基础。字段重命名可能被识别为删除加新增，手写数据迁移无法由 autogenerate 重建；用户已明确接受这一破坏风险。

Vercel 多实例冷启动仍可能同时生成迁移。此次实现只处理已确认的缺失 revision 故障，不扩展为分布式迁移锁。

## 验证

- 测试确认脚本包含定向识别、`stamp head --purge` 和原有迁移顺序。
- 测试确认非缺失 revision 错误不会进入恢复分支。
- 运行完整测试套件。
- 推送 `dev-vercel` 后重新部署 Preview，确认运行日志完成迁移且 `/health` 返回 200。
- Preview 验证通过后再提升到 Production，并再次验证生产 `/health`。
