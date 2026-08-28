"""Quality-screening workflow and public visibility tests."""

import importlib

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.hackathon import (
    Hackathon,
    HackathonDisplayStatus,
    HackathonMode,
    HackathonStatus,
)
from app.config import Settings
from app.crawler.llm_processor import StandardizedHackathon
from app.crawler.persistence import persist_batch


screening_module = importlib.import_module("app.crawler.screening_worker")
hackathon_service_module = importlib.import_module("app.services.hackathon_service")


def test_llm_provider_values_are_not_hard_coded_in_settings():
    isolated_settings = Settings(_env_file=None)

    assert isolated_settings.LLM_API_KEY == ""
    assert isolated_settings.LLM_API_BASE_URL == ""
    assert isolated_settings.LLM_MODEL == ""
    assert isolated_settings.LLM_SCREENING_API_BASE_URL == ""
    assert isolated_settings.LLM_SCREENING_MODEL == ""


async def _sqlite_sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Hackathon.__table__.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _hackathon(slug: str, display_status: HackathonDisplayStatus) -> Hackathon:
    return Hackathon(
        name=f"Event {slug}",
        slug=slug,
        source_url=f"https://example.com/{slug}",
        source_platform="test",
        status=HackathonStatus.UPCOMING,
        mode=HackathonMode.ONLINE,
        display_status=display_status,
    )


@pytest.mark.asyncio
async def test_public_queries_only_return_approved_hackathons(monkeypatch):
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            session.add_all(
                [
                    _hackathon("pending", HackathonDisplayStatus.PENDING),
                    _hackathon("approved", HackathonDisplayStatus.APPROVED),
                    _hackathon("rejected", HackathonDisplayStatus.REJECTED),
                ]
            )
            await session.commit()

        monkeypatch.setattr(hackathon_service_module, "async_session_factory", sessions)
        items, total = await hackathon_service_module.HackathonService.list_hackathons()
        hot = await hackathon_service_module.HackathonService.get_hot_list()

        assert total == 1
        assert [item["slug"] for item in items] == ["approved"]
        assert [item["slug"] for item in hot] == ["approved"]
        assert (
            await hackathon_service_module.HackathonService.get_hackathon("pending")
            is None
        )
        approved = await hackathon_service_module.HackathonService.get_hackathon(
            "approved"
        )
        assert approved is not None
    finally:
        await engine.dispose()


class _DecisionClient:
    def __init__(self, decision: bool | None):
        self.decision = decision
        self.events: list[dict] = []

    async def evaluate(self, event: dict) -> bool | None:
        self.events.append(event)
        return self.decision


@pytest.mark.asyncio
async def test_screening_worker_updates_pending_event(monkeypatch):
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            event = _hackathon("screen-me", HackathonDisplayStatus.PENDING)
            session.add(event)
            await session.commit()
            event_id = event.id

        monkeypatch.setattr(screening_module, "async_session_factory", sessions)
        client = _DecisionClient(True)
        worker = screening_module.HackathonScreeningWorker(client=client)
        await worker._screen_event(event_id)

        async with sessions() as session:
            status = await session.scalar(
                select(Hackathon.display_status).where(Hackathon.id == event_id)
            )
        assert status == HackathonDisplayStatus.APPROVED
        assert client.events[0]["source_url"].endswith("/screen-me")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_screening_failure_keeps_event_pending(monkeypatch):
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            event = _hackathon("retry-me", HackathonDisplayStatus.PENDING)
            session.add(event)
            await session.commit()
            event_id = event.id

        monkeypatch.setattr(screening_module, "async_session_factory", sessions)
        worker = screening_module.HackathonScreeningWorker(
            client=_DecisionClient(None)
        )
        await worker._screen_event(event_id)

        async with sessions() as session:
            status = await session.scalar(
                select(Hackathon.display_status).where(Hackathon.id == event_id)
            )
        assert status == HackathonDisplayStatus.PENDING
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_persisted_crawl_rows_are_pending_and_returned_for_queueing():
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            result = await persist_batch(
                session,
                [
                    StandardizedHackathon(
                        name="First Hackathon",
                        slug="first-hackathon",
                        source_url="https://example.com/first",
                        source_platform="test",
                    ),
                    StandardizedHackathon(
                        name="Second Hackathon",
                        slug="second-hackathon",
                        source_url="https://example.com/second",
                        source_platform="test",
                    ),
                ],
            )

        async with sessions() as session:
            statuses = list(
                (
                    await session.scalars(
                        select(Hackathon.display_status).order_by(Hackathon.id)
                    )
                ).all()
            )

        assert result.inserted == 2
        assert len(result.event_ids) == 2
        assert statuses == [
            HackathonDisplayStatus.PENDING,
            HackathonDisplayStatus.PENDING,
        ]
    finally:
        await engine.dispose()


def test_screening_client_uses_injected_model_and_url():
    client = screening_module.QualityScreeningClient(
        api_key="test-key",
        base_url="https://api.stepfun.com/step_plan",
        model="step-explore",
    )

    assert client.model == "step-explore"
    assert client.base_url == "https://api.stepfun.com/step_plan"


@pytest.mark.asyncio
async def test_screening_client_uses_anthropic_messages_protocol(monkeypatch):
    captured: dict = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": '{"approved": true, "reason": "valid"}',
                    }
                ]
            }

    class _AsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, json=json)
            return _Response()

    monkeypatch.setattr(screening_module.httpx, "AsyncClient", _AsyncClient)
    client = screening_module.QualityScreeningClient(
        api_key="test-key",
        base_url="https://api.stepfun.com/step_plan",
        model="step-explore",
    )

    decision = await client.evaluate({"name": "Valid Hackathon"})

    assert decision is True
    assert captured["url"] == "https://api.stepfun.com/step_plan/v1/messages"
    assert captured["json"]["model"] == "step-explore"
    assert captured["json"]["max_tokens"] == 256
    assert "thinking" not in captured["json"]
