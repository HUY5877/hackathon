"""Administrator hackathon-management contract tests."""

from datetime import datetime
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import require_admin
from app.api.v1.admin import router
from app.schemas.admin import AdminHackathonUpdate
from app.services.admin_service import (
    AdminConflictError,
    AdminNotFoundError,
    admin_service,
)


ADMIN = {"id": 1, "email": "admin@example.com", "role": "admin"}
HACKATHON = {
    "id": 3,
    "name": "AI Agents Hack 2026",
    "slug": "ai-agents-hack-2026",
    "description": "Build an agent product.",
    "summary": "An AI agent competition.",
    "registration_start": datetime(2026, 8, 1, 9, 0),
    "registration_end": datetime(2026, 8, 20, 18, 0),
    "event_start": datetime(2026, 8, 25, 9, 0),
    "event_end": datetime(2026, 8, 27, 18, 0),
    "status": "registering",
    "mode": "online",
    "track_tags": ["AI"],
    "tech_tags": ["Python"],
    "prize_pool": "$10,000",
    "prize_pool_usd": 10000.0,
    "expected_participants": 200,
    "location": "Online",
    "country": "Global",
    "city": None,
    "source_url": "https://devpost.com/example",
    "source_platform": "devpost",
    "registration_url": "https://devpost.com/register",
    "organizer": "Devpost",
    "sponsors": ["OpenAI"],
    "cover_image": "https://example.com/cover.png",
    "is_verified": False,
    "llm_confidence": 0.92,
    "display_status": "approved",
    "view_count": 12,
    "external_click_count": 3,
    "created_at": datetime(2026, 8, 2, 10, 0),
    "updated_at": datetime(2026, 8, 4, 11, 0),
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: ADMIN
    return TestClient(app)


def test_update_schema_rejects_source_fields():
    with pytest.raises(ValidationError):
        AdminHackathonUpdate(source_platform="manual")


def test_update_schema_rejects_empty_payload():
    with pytest.raises(ValidationError):
        AdminHackathonUpdate()


def test_update_schema_rejects_inverted_event_dates():
    with pytest.raises(ValidationError):
        AdminHackathonUpdate(
            event_start=datetime(2026, 9, 2),
            event_end=datetime(2026, 9, 1),
        )


def test_update_schema_rejects_non_http_urls():
    with pytest.raises(ValidationError):
        AdminHackathonUpdate(registration_url="javascript:alert(1)")


def test_list_hackathons_returns_paginated_management_records(monkeypatch):
    async def fake_list_hackathons(**filters):
        assert filters == {
            "keyword": "agent",
            "source_platform": "devpost",
            "status": "registering",
            "display_status": None,
            "page": 1,
            "page_size": 20,
        }
        return [HACKATHON], 1

    monkeypatch.setattr(admin_service, "list_hackathons", fake_list_hackathons)

    response = _client().get(
        "/admin/hackathons?keyword=agent&source_platform=devpost&status=registering"
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["source_platform"] == "devpost"
    assert response.json()["data"]["total"] == 1


def test_get_hackathon_returns_not_found(monkeypatch):
    async def fake_get_hackathon(hackathon_id):
        raise AdminNotFoundError("赛事不存在")

    monkeypatch.setattr(admin_service, "get_hackathon", fake_get_hackathon)

    response = _client().get("/admin/hackathons/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "赛事不存在"


def test_update_hackathon_returns_changed_record_and_audit_log(monkeypatch, caplog):
    updated = {**HACKATHON, "name": "Updated Agent Hack"}

    async def fake_update_hackathon(hackathon_id, changes):
        assert hackathon_id == 3
        assert changes == {"name": "Updated Agent Hack"}
        return updated

    monkeypatch.setattr(admin_service, "update_hackathon", fake_update_hackathon)
    caplog.set_level(logging.INFO, logger="app.api.v1.admin")

    response = _client().post(
        "/admin/hackathons/3/update",
        json={"name": "Updated Agent Hack"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Updated Agent Hack"
    record = next(r for r in caplog.records if getattr(r, "operation", None) == "update_hackathon")
    assert record.actor_id == 1
    assert record.target_id == 3


def test_delete_requires_exact_current_name(monkeypatch):
    async def fake_delete_hackathon(hackathon_id, confirm_name):
        raise AdminConflictError("赛事名称确认不匹配")

    monkeypatch.setattr(admin_service, "delete_hackathon", fake_delete_hackathon)

    response = _client().post(
        "/admin/hackathons/3/delete",
        json={"confirm_name": "Wrong name"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "赛事名称确认不匹配"


def test_delete_returns_removed_identity_and_audit_log(monkeypatch, caplog):
    async def fake_delete_hackathon(hackathon_id, confirm_name):
        assert confirm_name == HACKATHON["name"]
        return {"id": hackathon_id, "name": confirm_name}

    monkeypatch.setattr(admin_service, "delete_hackathon", fake_delete_hackathon)
    caplog.set_level(logging.INFO, logger="app.api.v1.admin")

    response = _client().post(
        "/admin/hackathons/3/delete",
        json={"confirm_name": HACKATHON["name"]},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"id": 3, "name": HACKATHON["name"]}
    record = next(r for r in caplog.records if getattr(r, "operation", None) == "delete_hackathon")
    assert record.actor_id == 1
    assert record.target_id == 3
