# Vercel Alembic 缺失 Revision 恢复设计

## 目标

Vercel 容器省略普通服务器启动流程中的第一次 `alembic upgrade head`，避免重复的缺失 revision 检查耗尽 15 秒端口启动期限。若后续步骤仅因数据库指向镜像中不存在的 revision 而失败，记录警告并继续应用启动；不修改或重置数据库中的 Alembic 版本指针。

## 启动流程

1. 在同一个 Python 进程中执行等价于 `alembic revision --autogenerate -m "auto"` 的操作。
2. 在同一进程中继续执行等价于 `alembic upgrade head` 的操作。
3. 启动 Uvicorn。

两个 Alembic 操作共享解释器和已导入模块，以减少远程数据库冷启动期间的重复开销；执行顺序、Alembic 配置和数据库语义保持不变。

两个 Alembic 步骤统一检查执行结果：若失败输出包含 `Can't locate revision identified by`，输出明确警告并继续；其他数据库连接、权限、差异生成或迁移代码错误仍直接退出容器。

## 修改范围

- 迁移编排放在 `vercel_migrations.py`，`entrypoint.vercel.sh` 只调用一次 Python 迁移进程后启动 Uvicorn。
- 自动化测试同时约束入口调用方式、迁移顺序和错误处理边界。
- 不修改、删除或提交工作区现有的 `alembic/versions/*.py` 未跟踪文件。
- 不修改普通 Docker Compose 的服务配置。
- Vercel 环境变量和数据库连接保持当前配置。

## 错误与风险

该流程不会修复缺失 revision。autogenerate 和 upgrade 都可能因同一缺失 revision 被跳过，应用会在数据库 Schema 未与当前 models 对齐的情况下启动；依赖缺失表、字段或约束的 API 可能在运行时失败。用户已明确接受这一风险。

当 Alembic 历史完整时，Vercel 多实例冷启动仍可能同时生成迁移。此次实现仅忽略已确认的缺失 revision 错误，不扩展为分布式迁移锁。

## 验证

- 测试确认 Vercel 执行 `autogenerate → upgrade head → Uvicorn`，且不执行首次 `upgrade head`。
- 测试确认仅缺失 revision 错误会被忽略，其他 Alembic 错误仍退出容器。
- 运行完整测试套件。
- 推送 `dev-vercel` 后重新部署 Preview，确认运行日志完成迁移且 `/health` 返回 200。
- Preview 验证通过后再提升到 Production，并再次验证生产 `/health`。
