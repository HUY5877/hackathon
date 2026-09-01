"""Manual crawler task tracking, progress, and locking tests."""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.crawler.base import CrawlResult
from app.crawler.task_manager import CrawlerTaskConflict, CrawlerTaskManager


class ProgressScheduler:
    def __init__(self):
        self.persist_argument = None

    def is_platform_running(self, platform):
        return False

    def is_all_running(self):
        return False

    async def run_platform(
        self,
        platform,
        *,
        save_json,
        persist,
        progress_callback,
    ):
        self.persist_argument = persist
        progress_callback(
            progress=15,
            phase="fetching",
            message=f"正在抓取 {platform}",
            current_platform=platform,
        )
        progress_callback(
            progress=55,
            phase="cleaning",
            message=f"正在清洗 {platform}",
            current_platform=platform,
        )
        return {"platform": platform, "status": "success", "cleaned_count": 4}

    async def run_all_with_dedup(self, *, save_json, progress_callback):
        progress_callback(
            progress=50,
            phase="cleaning",
            message="正在清洗 devpost",
            current_platform="devpost",
            completed_platforms=1,
            total_platforms=2,
        )
        return {"summary": {"success_platforms": 2, "error_platforms": 0}}


class BlockingScheduler(ProgressScheduler):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run_platform(self, *args, **kwargs):
        self.started.set()
        await self.release.wait()
        return {"platform": args[0], "status": "success"}


class FailingScheduler(ProgressScheduler):
    async def run_platform(self, *args, **kwargs):
        raise RuntimeError("crawler exploded")


@pytest.mark.asyncio
async def test_platform_task_reports_progress_and_persists_results():
    scheduler = ProgressScheduler()
    manager = CrawlerTaskManager(scheduler=scheduler)

    queued = manager.create(scope="platform", platform="devpost", actor_id=1)
    completed = await manager.wait(queued.task_id)

    assert scheduler.persist_argument is True
    assert completed.status == "completed"
    assert completed.phase == "completed"
    assert completed.progress == 100
    assert completed.result["cleaned_count"] == 4


@pytest.mark.asyncio
async def test_full_task_reports_platform_counts():
    manager = CrawlerTaskManager(scheduler=ProgressScheduler())

    queued = manager.create(scope="all", platform=None, actor_id=1)
    completed = await manager.wait(queued.task_id)

    assert completed.status == "completed"
    assert completed.progress == 100
    assert completed.completed_platforms == 2
    assert completed.total_platforms == 2


@pytest.mark.asyncio
async def test_duplicate_platform_task_conflicts_while_first_is_running():
    scheduler = BlockingScheduler()
    manager = CrawlerTaskManager(scheduler=scheduler)

    first = manager.create(scope="platform", platform="devpost", actor_id=1)
    await scheduler.started.wait()

    with pytest.raises(CrawlerTaskConflict, match="devpost"):
        manager.create(scope="platform", platform="devpost", actor_id=2)

    scheduler.release.set()
    await manager.wait(first.task_id)


@pytest.mark.asyncio
async def test_task_exception_becomes_failed_snapshot():
    manager = CrawlerTaskManager(scheduler=FailingScheduler())

    queued = manager.create(scope="platform", platform="devpost", actor_id=1)
    failed = await manager.wait(queued.task_id)

    assert failed.status == "failed"
    assert failed.phase == "failed"
    assert failed.progress == 5
    assert failed.error == "crawler exploded"


@pytest.mark.asyncio
async def test_task_history_retains_only_latest_completed_snapshots():
    manager = CrawlerTaskManager(scheduler=ProgressScheduler(), max_tasks=3)
    created_ids = []
    for _ in range(5):
        queued = manager.create(scope="platform", platform="devpost", actor_id=1)
        created_ids.append(queued.task_id)
        await manager.wait(queued.task_id)

    retained_ids = [task.task_id for task in manager.list_tasks()]

    assert retained_ids == list(reversed(created_ids[-3:]))


class FakeCrawler:
    def __init__(self, name, calls, release=None):
        self.name = name
        self.calls = calls
        self.release = release

    async def run(self, max_items=None):
        self.calls.append(self.name)
        if self.release is not None:
            await self.release.wait()
        return [
            CrawlResult(
                source_platform=self.name,
                source_url=f"https://example.com/{self.name}",
                raw_title=f"{self.name} hackathon",
                raw_data={"mode": "online"},
            )
        ]


@pytest.mark.asyncio
async def test_scheduler_platform_progress_and_shared_lock(monkeypatch):
    from app.crawler.scheduler import CrawlerBusyError, CrawlerScheduler

    scheduler_module = importlib.import_module("app.crawler.scheduler")
    calls = []
    release = asyncio.Event()
    monkeypatch.setattr(
        scheduler_module,
        "CRAWLER_REGISTRY",
        {"test": FakeCrawler("test", calls, release=release)},
    )
    scheduler = CrawlerScheduler()
    progress = []
    first = asyncio.create_task(
        scheduler.run_platform(
            "test",
            save_json=False,
            persist=False,
            progress_callback=lambda **state: progress.append(state),
        )
    )
    while not calls:
        await asyncio.sleep(0)

    with pytest.raises(CrawlerBusyError, match="test"):
        await scheduler.run_platform("test", save_json=False)

    release.set()
    result = await first

    assert result["status"] == "success"
    assert [state["progress"] for state in progress] == [15, 95, 100]
    assert all(state["phase"] != "cleaning" for state in progress)


@pytest.mark.asyncio
async def test_scheduler_persists_source_data_then_enqueues_llm_work(monkeypatch):
    from app.crawler.scheduler import CrawlerScheduler

    scheduler_module = importlib.import_module("app.crawler.scheduler")
    captured = {}

    class SourceCrawler:
        async def run(self, max_items=None):
            return [
                CrawlResult(
                    source_platform="source",
                    source_url="https://example.com/event",
                    raw_title="Source Event",
                    raw_description="Original description",
                    raw_data={
                        "start_date": "2026-09-01",
                        "end_date": "2026-09-02",
                        "organizer": "Source Organizer",
                    },
                )
            ]

    async def fake_persist_batch(session, items):
        captured["items"] = items
        return SimpleNamespace(
            event_ids=[42],
            to_dict=lambda: {
                "inserted": 1,
                "updated": 0,
                "skipped": 0,
                "errors": [],
                "total": 1,
            },
        )

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(scheduler_module, "CRAWLER_REGISTRY", {"source": SourceCrawler()})
    monkeypatch.setattr(scheduler_module, "persist_batch", fake_persist_batch)
    monkeypatch.setattr(scheduler_module, "async_session_factory", lambda: FakeSessionContext())
    monkeypatch.setattr(
        scheduler_module.screening_worker,
        "enqueue",
        lambda event_ids: captured.setdefault("event_ids", list(event_ids)),
    )
    progress = []

    result = await CrawlerScheduler().run_platform(
        "source",
        save_json=False,
        persist=True,
        progress_callback=lambda **state: progress.append(state),
    )

    assert result["status"] == "success"
    assert captured["event_ids"] == [42]
    assert len(captured["items"]) == 1
    persisted = captured["items"][0]
    assert persisted.name == "Source Event"
    assert persisted.description == "Original description"
    assert persisted.event_start == "2026-09-01"
    assert persisted.organizer == "Source Organizer"
    assert persisted.llm_confidence == 0.0
    assert all(state["phase"] != "cleaning" for state in progress)


@pytest.mark.asyncio
async def test_scheduler_rejects_failed_and_incomplete_results_before_persistence(monkeypatch):
    from app.crawler.scheduler import CrawlerScheduler

    scheduler_module = importlib.import_module("app.crawler.scheduler")

    class InvalidCrawler:
        async def run(self, max_items=None):
            return [
                CrawlResult(
                    source_platform="source",
                    source_url="https://example.com/failed",
                    raw_title="",
                    success=False,
                    error_message="blocked",
                ),
                CrawlResult(
                    source_platform="source",
                    source_url="https://example.com/missing-title",
                    raw_title="",
                ),
            ]

    persist_mock = AsyncMock()
    monkeypatch.setattr(scheduler_module, "CRAWLER_REGISTRY", {"source": InvalidCrawler()})
    monkeypatch.setattr(scheduler_module, "persist_batch", persist_mock)
    monkeypatch.setattr(CrawlerScheduler, "_alert_failure", AsyncMock())

    result = await CrawlerScheduler().run_platform(
        "source", save_json=False, persist=True
    )

    assert result["status"] == "error"
    assert result["raw_count"] == 2
    assert result["failed_count"] == 1
    assert result["invalid_count"] == 1
    assert result["mapped_count"] == 0
    persist_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_full_run_visits_every_registered_platform(monkeypatch):
    from app.crawler.scheduler import CrawlerScheduler

    scheduler_module = importlib.import_module("app.crawler.scheduler")
    calls = []
    monkeypatch.setattr(
        scheduler_module,
        "CRAWLER_REGISTRY",
        {
            "alpha": FakeCrawler("alpha", calls),
            "beta": FakeCrawler("beta", calls),
        },
    )

    async def fake_persist_batch(session, items):
        return SimpleNamespace(
            event_ids=[],
            to_dict=lambda: {"inserted": 0, "updated": 0, "skipped": 0, "errors": []},
        )

    async def no_sleep(_seconds):
        return None

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(scheduler_module, "persist_batch", fake_persist_batch)
    monkeypatch.setattr(scheduler_module, "async_session_factory", lambda: FakeSessionContext())
    monkeypatch.setattr(scheduler_module.asyncio, "sleep", no_sleep)
    scheduler = CrawlerScheduler()
    progress = []

    result = await scheduler.run_all_with_dedup(
        save_json=False,
        progress_callback=lambda **state: progress.append(state),
    )

    assert calls == ["alpha", "beta"]
    assert result["summary"]["total_platforms"] == 2
    assert progress[-1]["progress"] == 100
    assert progress[-1]["phase"] == "completed"


@pytest.mark.asyncio
async def test_scheduled_platform_run_persists_before_async_screening(monkeypatch):
    scheduler_manager_module = importlib.import_module("app.crawler.apscheduler_manager")
    captured = {}

    class CapturingScheduler:
        async def run_platform(self, platform, **kwargs):
            captured["platform"] = platform
            captured["kwargs"] = kwargs
            return {
                "platform": platform,
                "status": "success",
                "raw_count": 1,
                "mapped_count": 1,
            }

    monkeypatch.setattr(
        scheduler_manager_module,
        "crawler_scheduler",
        CapturingScheduler(),
    )

    result = await scheduler_manager_module.SchedulerManager()._run_platform_safe("mlh")

    assert result["status"] == "success"
    assert captured == {
        "platform": "mlh",
        "kwargs": {"save_json": True, "persist": True},
    }
