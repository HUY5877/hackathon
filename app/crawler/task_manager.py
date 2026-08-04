"""In-process tracking for administrator-triggered crawler tasks."""

import asyncio
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.crawler.scheduler import scheduler as default_scheduler


class CrawlerTaskConflict(RuntimeError):
    """Raised when a crawler target is already running."""


class CrawlerTaskNotFound(LookupError):
    """Raised when a task ID is no longer retained."""


@dataclass
class CrawlerTaskSnapshot:
    task_id: str
    scope: str
    platform: str | None
    actor_id: int
    status: str = "queued"
    phase: str = "queued"
    progress: int = 5
    message: str = "任务已加入队列"
    current_platform: str | None = None
    completed_platforms: int = 0
    total_platforms: int = 0
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CrawlerTaskManager:
    """Launch and retain a bounded set of manual crawler task snapshots."""

    def __init__(self, scheduler=default_scheduler, max_tasks: int = 100):
        self._scheduler = scheduler
        self._max_tasks = max_tasks
        self._tasks: OrderedDict[str, CrawlerTaskSnapshot] = OrderedDict()
        self._futures: dict[str, asyncio.Task] = {}
        self._active_platforms: set[str] = set()
        self._all_active = False

    def create(
        self,
        *,
        scope: str,
        platform: str | None,
        actor_id: int,
    ) -> CrawlerTaskSnapshot:
        if scope not in {"platform", "all"}:
            raise ValueError("scope 必须是 platform 或 all")
        if scope == "platform" and not platform:
            raise ValueError("单平台任务必须指定 platform")

        if scope == "platform":
            assert platform is not None
            if (
                self._all_active
                or platform in self._active_platforms
                or self._scheduler.is_platform_running(platform)
            ):
                raise CrawlerTaskConflict(f"平台 {platform} 正在运行")
            self._active_platforms.add(platform)
        else:
            any_scheduler_platform = getattr(
                self._scheduler, "any_platform_running", lambda: False
            )()
            if (
                self._all_active
                or self._active_platforms
                or self._scheduler.is_all_running()
                or any_scheduler_platform
            ):
                raise CrawlerTaskConflict("已有爬虫任务正在运行")
            self._all_active = True

        self._prune_completed()
        task_id = uuid4().hex
        snapshot = CrawlerTaskSnapshot(
            task_id=task_id,
            scope=scope,
            platform=platform,
            actor_id=actor_id,
        )
        self._tasks[task_id] = snapshot
        future = asyncio.get_running_loop().create_task(self._run(snapshot))
        self._futures[task_id] = future
        return snapshot

    def get_task(self, task_id: str) -> CrawlerTaskSnapshot:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise CrawlerTaskNotFound("爬虫任务不存在或已清理") from exc

    def list_tasks(self, status: str | None = None) -> list[CrawlerTaskSnapshot]:
        tasks = reversed(self._tasks.values())
        if status is None:
            return list(tasks)
        return [task for task in tasks if task.status == status]

    async def wait(self, task_id: str) -> CrawlerTaskSnapshot:
        self.get_task(task_id)
        future = self._futures.get(task_id)
        if future is not None:
            await future
        return self.get_task(task_id)

    async def _run(self, snapshot: CrawlerTaskSnapshot) -> None:
        snapshot.status = "running"
        snapshot.started_at = datetime.now()

        def report_progress(**state) -> None:
            snapshot.progress = max(0, min(100, int(state["progress"])))
            snapshot.phase = state["phase"]
            snapshot.message = state.get("message") or snapshot.message
            snapshot.current_platform = state.get("current_platform")
            if state.get("completed_platforms") is not None:
                snapshot.completed_platforms = state["completed_platforms"]
            if state.get("total_platforms") is not None:
                snapshot.total_platforms = state["total_platforms"]

        try:
            if snapshot.scope == "platform":
                result = await self._scheduler.run_platform(
                    snapshot.platform,
                    save_json=True,
                    persist=True,
                    progress_callback=report_progress,
                )
                if result.get("status") == "error":
                    raise RuntimeError(result.get("error") or "爬虫任务失败")
            else:
                result = await self._scheduler.run_all_with_dedup(
                    save_json=True,
                    progress_callback=report_progress,
                )
            snapshot.result = result
            snapshot.status = "completed"
            snapshot.phase = "completed"
            snapshot.progress = 100
            snapshot.message = "爬虫任务已完成"
            if snapshot.total_platforms:
                snapshot.completed_platforms = snapshot.total_platforms
        except Exception as exc:
            snapshot.status = "failed"
            snapshot.phase = "failed"
            snapshot.message = "爬虫任务执行失败"
            snapshot.error = str(exc)
        finally:
            snapshot.completed_at = datetime.now()
            if snapshot.scope == "platform" and snapshot.platform:
                self._active_platforms.discard(snapshot.platform)
            else:
                self._all_active = False

    def _prune_completed(self) -> None:
        while len(self._tasks) >= self._max_tasks:
            removable_id = next(
                (
                    task_id
                    for task_id, task in self._tasks.items()
                    if task.status in {"completed", "failed"}
                ),
                None,
            )
            if removable_id is None:
                return
            self._tasks.pop(removable_id, None)
            self._futures.pop(removable_id, None)

crawler_task_manager = CrawlerTaskManager()
