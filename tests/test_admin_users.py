"""Administrator user-management API contract tests."""

from datetime import datetime
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_admin
from app.api.v1.admin import router
from app.services.admin_service import (
    AdminConflictError,
    AdminNotFoundError,
    admin_service,
)


ADMIN = {"id": 1, "email": "admin@example.com", "role": "admin"}
DEVELOPER = {
    "id": 2,
    "email": "dev@example.com",
    "username": "dev",
    "role": "developer",
    "email_verified": True,
    "created_at": datetime(2026, 8, 4, 12, 0),
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: ADMIN
    return TestClient(app)


def test_list_users_returns_safe_paginated_records(monkeypatch):
    async def fake_list_users(*, keyword, page, page_size):
        assert keyword == "dev"
        assert page == 2
        assert page_size == 10
        return [DEVELOPER], 11

    monkeypatch.setattr(admin_service, "list_users", fake_list_users)

    response = _client().get("/admin/users?keyword=dev&page=2&page_size=10")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "items": [{**DEVELOPER, "created_at": "2026-08-04T12:00:00"}],
        "total": 11,
        "page": 2,
        "page_size": 10,
        "total_pages": 2,
    }
    assert "hashed_password" not in data["items"][0]


def test_promote_user_returns_updated_admin_record(monkeypatch):
    promoted = {**DEVELOPER, "role": "admin"}

    async def fake_promote_user(user_id):
        assert user_id == 2
        return promoted

    monkeypatch.setattr(admin_service, "promote_user", fake_promote_user)

    response = _client().post("/admin/users/2/promote")

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "admin"


def test_promote_missing_user_returns_not_found(monkeypatch):
    async def fake_promote_user(user_id):
        raise AdminNotFoundError("用户不存在")

    monkeypatch.setattr(admin_service, "promote_user", fake_promote_user)

    response = _client().post("/admin/users/999/promote")

    assert response.status_code == 404
    assert response.json()["detail"] == "用户不存在"


def test_promote_existing_admin_returns_conflict(monkeypatch):
    async def fake_promote_user(user_id):
        raise AdminConflictError("该用户已经是管理员")

    monkeypatch.setattr(admin_service, "promote_user", fake_promote_user)

    response = _client().post("/admin/users/1/promote")

    assert response.status_code == 409
    assert response.json()["detail"] == "该用户已经是管理员"


def test_promote_user_writes_structured_audit_log(monkeypatch, caplog):
    async def fake_promote_user(user_id):
        return {**DEVELOPER, "role": "admin"}

    monkeypatch.setattr(admin_service, "promote_user", fake_promote_user)
    caplog.set_level(logging.INFO, logger="app.api.v1.admin")

    response = _client().post("/admin/users/2/promote")

    assert response.status_code == 200
    audit_records = [
        record for record in caplog.records
        if getattr(record, "operation", None) == "promote_user"
    ]
    assert len(audit_records) == 1
    assert audit_records[0].actor_id == 1
    assert audit_records[0].target_id == 2
