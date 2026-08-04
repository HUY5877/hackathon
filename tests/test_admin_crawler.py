"""Administrator crawler-control API contract tests."""

from datetime import datetime
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, require_admin
from app.api.v1.admin import router as admin_router
from app.api.v1.crawler import router as crawler_router
from app.crawler.scheduler import CRAWLER_REGISTRY, CRAWL_SCHEDULE, scheduler
from app.crawler.task_manager import (
    CrawlerTaskConflict,
    CrawlerTaskNotFound,
    CrawlerTaskSnapshot,
    crawler_task_manager,
)


ADMIN = {"id": 1, "email": "admin@example.com", "role": "admin"}
DEVELOPER = {"id": 2, "email": "dev@example.com", "role": "developer"}


def _admin_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[require_admin] = lambda: ADMIN
    return app


def _snapshot(**overrides) -> CrawlerTaskSnapshot:
    values = {
        "task_id": "task-1",
        "scope": "platform",
        "platform": "devpost",
        "actor_id": 1,
        "created_at": datetime(2026, 8, 4, 12, 0),
    }
    values.update(overrides)
    return CrawlerTaskSnapshot(**values)


def test_create_platform_task_returns_202(monkeypatch):
    def fake_create(*, scope, platform, actor_id):
        assert (scope, platform, actor_id) == ("platform", "devpost", 1)
        return _snapshot()

    monkeypatch.setattr(crawler_task_manager, "create", fake_create)

    response = TestClient(_admin_app()).post(
        "/admin/crawler/tasks",
        json={"scope": "platform", "platform": "devpost"},
    )

    assert response.status_code == 202
    assert response.json()["data"] == {
        "task_id": "task-1",
        "scope": "platform",
        "platform": "devpost",
        "actor_id": 1,
        "status": "queued",
        "phase": "queued",
        "progress": 5,
        "message": "任务已加入队列",
        "current_platform": None,
        "completed_platforms": 0,
        "total_platforms": 0,
        "result": None,
        "error": None,
        "created_at": "2026-08-04T12:00:00",
        "started_at": None,
        "completed_at": None,
    }


def test_create_all_task_ignores_platform(monkeypatch):
    def fake_create(*, scope, platform, actor_id):
        assert (scope, platform, actor_id) == ("all", None, 1)
        return _snapshot(scope="all", platform=None)

    monkeypatch.setattr(crawler_task_manager, "create", fake_create)

    response = TestClient(_admin_app()).post(
        "/admin/crawler/tasks",
        json={"scope": "all"},
    )

    assert response.status_code == 202
    assert response.json()["data"]["scope"] == "all"


def test_create_task_rejects_unknown_platform():
    response = TestClient(_admin_app()).post(
        "/admin/crawler/tasks",
        json={"scope": "platform", "platform": "unknown"},
    )

    assert response.status_code == 404


def test_create_task_maps_running_conflict_to_409(monkeypatch):
    def fake_create(**_):
        raise CrawlerTaskConflict("平台 devpost 正在运行")

    monkeypatch.setattr(crawler_task_manager, "create", fake_create)

    response = TestClient(_admin_app()).post(
        "/admin/crawler/tasks",
        json={"scope": "platform", "platform": "devpost"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "平台 devpost 正在运行"


def test_create_task_requires_platform_for_platform_scope():
    response = TestClient(_admin_app()).post(
        "/admin/crawler/tasks",
        json={"scope": "platform"},
    )

    assert response.status_code == 422


def test_create_task_writes_structured_audit_log(monkeypatch, caplog):
    monkeypatch.setattr(crawler_task_manager, "create", lambda **_: _snapshot())
    caplog.set_level(logging.INFO, logger="app.api.v1.admin")

    response = TestClient(_admin_app()).post(
        "/admin/crawler/tasks",
        json={"scope": "platform", "platform": "devpost"},
    )

    assert response.status_code == 202
    audit_records = [
        record
        for record in caplog.records
        if getattr(record, "operation", None) == "trigger_crawler"
    ]
    assert len(audit_records) == 1
    assert audit_records[0].actor_id == 1
    assert audit_records[0].target_id == "task-1"
    assert audit_records[0].target_platform == "devpost"


def test_list_and_get_tasks(monkeypatch):
    completed = _snapshot(task_id="task-2", status="completed", progress=100)
    monkeypatch.setattr(
        crawler_task_manager,
        "list_tasks",
        lambda status=None: [completed] if status == "completed" else [],
    )
    monkeypatch.setattr(crawler_task_manager, "get_task", lambda task_id: completed)
    client = TestClient(_admin_app())

    listed = client.get("/admin/crawler/tasks?status=completed")
    detail = client.get("/admin/crawler/tasks/task-2")

    assert listed.status_code == 200
    assert listed.json()["data"][0]["task_id"] == "task-2"
    assert detail.status_code == 200
    assert detail.json()["data"]["progress"] == 100


def test_get_missing_task_returns_404(monkeypatch):
    def fake_get(_task_id):
        raise CrawlerTaskNotFound("爬虫任务不存在或已清理")

    monkeypatch.setattr(crawler_task_manager, "get_task", fake_get)

    response = TestClient(_admin_app()).get("/admin/crawler/tasks/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "爬虫任务不存在或已清理"


def test_crawler_overview_uses_registry_schedules_and_history(monkeypatch):
    monkeypatch.setattr(scheduler, "get_history", lambda limit=20: [{"platform": "devpost"}])

    response = TestClient(_admin_app()).get("/admin/crawler/overview")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["platforms"] == list(CRAWLER_REGISTRY)
    assert data["schedules"] == CRAWL_SCHEDULE
    assert data["recent_runs"] == [{"platform": "devpost"}]
    assert isinstance(data["scheduler_running"], bool)
    assert isinstance(data["jobs"], list)


def test_admin_routes_do_not_expose_patch_or_delete_methods():
    app = _admin_app()
    methods = {
        method
        for route in app.routes
        if route.path.startswith("/admin")
        for method in route.methods
    }

    assert methods <= {"GET", "POST", "HEAD", "OPTIONS"}


def test_legacy_crawler_mutations_require_admin():
    app = FastAPI()
    app.include_router(crawler_router)
    app.dependency_overrides[get_current_user] = lambda: DEVELOPER

    response = TestClient(app).post("/crawler/circuit/reset")

    assert response.status_code == 403
