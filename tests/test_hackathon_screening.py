"""Quality-screening, cleaning workflow and public visibility tests."""

import importlib
from datetime import datetime

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


def _hackathon(
    slug: str,
    display_status: HackathonDisplayStatus,
    *,
    is_cleaned: bool = False,
) -> Hackathon:
    return Hackathon(
        name=f"Event {slug}",
        slug=slug,
        source_url=f"https://example.com/{slug}",
        source_platform="test",
        status=HackathonStatus.UPCOMING,
        mode=HackathonMode.ONLINE,
        display_status=display_status,
        is_cleaned=is_cleaned,
    )


@pytest.mark.asyncio
async def test_public_queries_only_return_approved_and_cleaned_hackathons(monkeypatch):
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            session.add_all(
                [
                    _hackathon("pending", HackathonDisplayStatus.PENDING),
                    _hackathon(
                        "approved-cleaned",
                        HackathonDisplayStatus.APPROVED,
                        is_cleaned=True,
                    ),
                    _hackathon("approved-unclean", HackathonDisplayStatus.APPROVED),
                    _hackathon("rejected", HackathonDisplayStatus.REJECTED),
                ]
            )
            await session.commit()

        monkeypatch.setattr(hackathon_service_module, "async_session_factory", sessions)
        items, total = await hackathon_service_module.HackathonService.list_hackathons()
        hot = await hackathon_service_module.HackathonService.get_hot_list()

        assert total == 1
        assert [item["slug"] for item in items] == ["approved-cleaned"]
        assert [item["slug"] for item in hot] == ["approved-cleaned"]
        assert (
            await hackathon_service_module.HackathonService.get_hackathon("pending")
            is None
        )
        approved = await hackathon_service_module.HackathonService.get_hackathon(
            "approved-cleaned"
        )
        assert approved is not None
        assert (
            await hackathon_service_module.HackathonService.get_hackathon(
                "approved-unclean"
            )
            is None
        )
    finally:
        await engine.dispose()


class _DecisionClient:
    def __init__(self, decision: bool | None):
        self.decision = decision
        self.events: list[dict] = []

    async def evaluate(self, event: dict) -> bool | None:
        self.events.append(event)
        return self.decision


class _CleaningClient:
    def __init__(self, result: dict | None):
        self.result = result
        self.events: list[dict] = []

    async def clean(self, event: dict) -> dict | None:
        self.events.append(event)
        return self.result


@pytest.mark.asyncio
async def test_screening_worker_updates_pending_event(monkeypatch, caplog):
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            event = _hackathon("screen-me", HackathonDisplayStatus.PENDING)
            event.raw_data = {"organizer": "Official Organizer"}
            session.add(event)
            await session.commit()
            event_id = event.id

        monkeypatch.setattr(screening_module, "async_session_factory", sessions)
        client = _DecisionClient(True)
        cleaning_client = _CleaningClient(
            {
                "name": "Clean Event",
                "summary": "A readable summary.",
                "description": "A clean event description.",
                "missing_fields": {"organizer": "Official Organizer"},
            }
        )
        worker = screening_module.HackathonScreeningWorker(
            client=client,
            cleaning_client=cleaning_client,
        )
        caplog.set_level("INFO", logger=screening_module.__name__)
        await worker._screen_event(event_id)

        async with sessions() as session:
            stored = await session.scalar(
                select(Hackathon).where(Hackathon.id == event_id)
            )
        assert stored.display_status == HackathonDisplayStatus.APPROVED
        assert stored.is_cleaned is True
        assert stored.name == "Clean Event"
        assert stored.organizer == "Official Organizer"
        assert client.events[0]["source_url"].endswith("/screen-me")
        assert cleaning_client.events[0]["source_url"].endswith("/screen-me")
        assert f"开始筛选：id={event_id}，名称=Event screen-me" in caplog.text
        assert (
            f"筛选完成：id={event_id}，名称=Event screen-me，结果=通过"
            in caplog.text
        )
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
            client=_DecisionClient(None),
            cleaning_client=_CleaningClient({}),
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
async def test_rejected_event_is_not_cleaned(monkeypatch):
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            event = _hackathon("reject-me", HackathonDisplayStatus.PENDING)
            session.add(event)
            await session.commit()
            event_id = event.id

        monkeypatch.setattr(screening_module, "async_session_factory", sessions)
        cleaning_client = _CleaningClient({"name": "must not run"})
        worker = screening_module.HackathonScreeningWorker(
            client=_DecisionClient(False),
            cleaning_client=cleaning_client,
        )
        await worker._screen_event(event_id)

        async with sessions() as session:
            stored = await session.scalar(
                select(Hackathon).where(Hackathon.id == event_id)
            )
        assert stored.display_status == HackathonDisplayStatus.REJECTED
        assert stored.is_cleaned is False
        assert cleaning_client.events == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cleaning_failure_keeps_approved_event_waiting(monkeypatch):
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            event = _hackathon("clean-later", HackathonDisplayStatus.APPROVED)
            session.add(event)
            await session.commit()
            event_id = event.id

        monkeypatch.setattr(screening_module, "async_session_factory", sessions)
        worker = screening_module.HackathonScreeningWorker(
            client=_DecisionClient(True),
            cleaning_client=_CleaningClient(None),
        )
        await worker._clean_event(event_id)

        async with sessions() as session:
            stored = await session.scalar(
                select(Hackathon).where(Hackathon.id == event_id)
            )
        assert stored.display_status == HackathonDisplayStatus.APPROVED
        assert stored.is_cleaned is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scan_pending_recovers_screening_and_cleaning_work(monkeypatch):
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            session.add_all(
                [
                    _hackathon("pending", HackathonDisplayStatus.PENDING),
                    _hackathon("clean-me", HackathonDisplayStatus.APPROVED),
                    _hackathon(
                        "done",
                        HackathonDisplayStatus.APPROVED,
                        is_cleaned=True,
                    ),
                    _hackathon("rejected", HackathonDisplayStatus.REJECTED),
                ]
            )
            await session.commit()

        monkeypatch.setattr(screening_module, "async_session_factory", sessions)
        worker = screening_module.HackathonScreeningWorker(
            client=_DecisionClient(True),
            cleaning_client=_CleaningClient({}),
        )
        queued: list[int] = []

        def capture_enqueue(event_ids):
            values = list(event_ids)
            queued.extend(values)
            return len(values)

        monkeypatch.setattr(worker, "enqueue", capture_enqueue)
        enqueued = await worker.scan_pending()

        async with sessions() as session:
            rows = (
                await session.execute(
                    select(Hackathon.id, Hackathon.slug).order_by(Hackathon.id)
                )
            ).all()
        slugs_by_id = dict(rows)
        assert enqueued == 2
        assert {slugs_by_id[event_id] for event_id in queued} == {
            "pending",
            "clean-me",
        }
    finally:
        await engine.dispose()


def test_cleaning_updates_preserve_existing_facts_and_system_fields():
    event = _hackathon("safe-clean", HackathonDisplayStatus.APPROVED)
    event.name = "Official Event - Site Navigation"
    event.description = "Official details plus unrelated ads"
    event.event_start = datetime(2026, 9, 1)
    event.organizer = "Original Organizer"
    event.source_url = "https://official.example/event"
    event.raw_data = {
        "country": "China",
        "city": "Beijing",
        "tracks": ["October 01 at 2:45am EDT to deadline"],
    }

    updates = screening_module._build_cleaning_updates(
        event,
        {
            "name": "Official Event",
            "summary": "Concise and readable.",
            "description": "Official event details.",
            "source_url": "https://attacker.example/changed",
            "display_status": "rejected",
            "missing_fields": {
                "event_start": "2030-01-01",
                "organizer": "Invented Organizer",
                "country": "China",
                "city": "Shanghai",
                "registration_url": "javascript:alert(1)",
                "track_tags": ["October 01 at 2:45am EDT to deadline"],
            },
        },
    )

    assert updates["name"] == "Official Event"
    assert updates["summary"] == "Concise and readable."
    assert updates["description"] == "Official event details."
    assert updates["country"] == "China"
    assert "event_start" not in updates
    assert "organizer" not in updates
    assert "city" not in updates
    assert "registration_url" not in updates
    assert "track_tags" not in updates
    assert "source_url" not in updates
    assert "display_status" not in updates


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
            states = list(
                (
                    await session.execute(
                        select(Hackathon.display_status, Hackathon.is_cleaned)
                        .order_by(Hackathon.id)
                    )
                ).all()
            )

        assert result.inserted == 2
        assert len(result.event_ids) == 2
        assert states == [
            (HackathonDisplayStatus.PENDING, False),
            (HackathonDisplayStatus.PENDING, False),
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_crawl_update_resets_screening_and_cleaning_state():
    engine, sessions = await _sqlite_sessions()
    try:
        async with sessions() as session:
            existing = _hackathon(
                "refresh-me",
                HackathonDisplayStatus.APPROVED,
                is_cleaned=True,
            )
            session.add(existing)
            await session.commit()
            event_id = existing.id

        async with sessions() as session:
            result = await persist_batch(
                session,
                [
                    StandardizedHackathon(
                        name="Event refresh-me",
                        slug="refresh-me",
                        summary="New source information",
                        source_url="https://example.com/refresh-me",
                        source_platform="test",
                    )
                ],
            )

        async with sessions() as session:
            stored = await session.scalar(
                select(Hackathon).where(Hackathon.id == event_id)
            )
        assert result.updated == 1
        assert result.event_ids == [event_id]
        assert stored.summary == "New source information"
        assert stored.display_status == HackathonDisplayStatus.PENDING
        assert stored.is_cleaned is False
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


def test_cleaning_client_uses_injected_model_and_url():
    client = screening_module.EventCleaningClient(
        api_key="test-key",
        base_url="https://api.stepfun.com/step_plan",
        model="step-explore",
    )

    assert client.model == "step-explore"
    assert client.base_url == "https://api.stepfun.com/step_plan"


@pytest.mark.asyncio
async def test_screening_client_uses_anthropic_messages_protocol(monkeypatch, caplog):
    captured: dict = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 20, "output_tokens": 30},
                "content": [
                    {"type": "thinking", "thinking": "brief reasoning"},
                    {
                        "type": "text",
                        "text": '{"approved": true, "reason": "valid"}\n',
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

    caplog.set_level("INFO", logger=screening_module.__name__)
    decision = await client.evaluate({"id": 7, "name": "Valid Hackathon"})

    assert decision is True
    assert captured["url"] == "https://api.stepfun.com/step_plan/v1/messages"
    assert captured["json"]["model"] == "step-explore"
    assert captured["json"]["max_tokens"] == 4096
    assert "thinking" not in captured["json"]
    assert "模型=step-explore，stop_reason=end_turn" in caplog.text
    assert "input_tokens=20，output_tokens=30" in caplog.text
    assert "content_types=['thinking', 'text']" in caplog.text
    assert '\\"approved\\": true' in caplog.text


@pytest.mark.asyncio
async def test_cleaning_client_uses_anthropic_messages_protocol(monkeypatch):
    captured: dict = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"name":"Clean Event","summary":"Readable",'
                            '"description":"Clean details","missing_fields":{}}'
                        ),
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
    client = screening_module.EventCleaningClient(
        api_key="test-key",
        base_url="https://api.stepfun.com/step_plan",
        model="step-explore",
    )

    result = await client.clean({"id": 9, "name": "Messy Event"})

    assert result["name"] == "Clean Event"
    assert captured["url"] == "https://api.stepfun.com/step_plan/v1/messages"
    assert captured["json"]["model"] == "step-explore"
    assert captured["json"]["max_tokens"] == 8192
    assert captured["timeout"] == 120
    prompt = captured["json"]["messages"][0]["content"]
    assert '"registration_start": null' not in prompt
    assert '"track_tags"' not in prompt


@pytest.mark.asyncio
async def test_screening_client_reports_token_limit_without_text(monkeypatch, caplog):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "stop_reason": "max_tokens",
                "content": [{"type": "thinking", "thinking": "still reasoning"}],
            }

    class _AsyncClient:
        def __init__(self, *, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, headers, json):
            return _Response()

    monkeypatch.setattr(screening_module.httpx, "AsyncClient", _AsyncClient)
    client = screening_module.QualityScreeningClient(
        api_key="test-key",
        base_url="https://api.stepfun.com/step_plan",
        model="step-explore",
    )
    caplog.set_level("WARNING", logger=screening_module.__name__)

    decision = await client.evaluate({"id": 8, "name": "Long Reasoning"})

    assert decision is None
    assert "模型输出达到 max_tokens=4096，响应可能不完整" in caplog.text


@pytest.mark.asyncio
async def test_cleaning_client_rejects_partial_text_at_token_limit(monkeypatch, caplog):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "stop_reason": "max_tokens",
                "usage": {"input_tokens": 762, "output_tokens": 8192},
                "content": [
                    {"type": "thinking", "thinking": "long reasoning"},
                    {"type": "text", "text": '{"name":"Half response"'},
                ],
            }

    class _AsyncClient:
        def __init__(self, *, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, headers, json):
            return _Response()

    monkeypatch.setattr(screening_module.httpx, "AsyncClient", _AsyncClient)
    client = screening_module.EventCleaningClient(
        api_key="test-key",
        base_url="https://api.stepfun.com/step_plan",
        model="step-3.7-flash",
    )
    caplog.set_level("INFO", logger=screening_module.__name__)

    result = await client.clean({"id": 9, "name": "Truncated Event"})

    assert result is None
    assert "stop_reason=max_tokens" in caplog.text
    assert "output_tokens=8192" in caplog.text
    assert "模型输出达到 max_tokens=8192，响应可能不完整" in caplog.text
