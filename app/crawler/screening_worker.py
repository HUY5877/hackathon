"""Asynchronous LLM quality screening for persisted hackathons.

The database status fields are the durable source of truth. The in-process
queue provides low-latency processing after a crawl, while the periodic scan
recovers screening and cleaning work after restarts or transient API failures.
"""

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx
from sqlalchemy import and_, or_, select, update

from app.config import settings
from app.crawler.llm_processor import _extract_json_from_text
from app.crawler.mapper import parse_date
from app.db.session import async_session_factory
from app.models.hackathon import Hackathon, HackathonDisplayStatus


logger = logging.getLogger(__name__)


SCREENING_PROMPT = """你是赛事内容质量审核员。请判断下面的数据是否适合展示在黑客松赛事信息平台。

通过标准：
1. 内容确实是黑客松、编程竞赛、创新挑战赛或 game jam，而不是新闻、课程、招聘或普通会议；
2. 名称和来源链接可信，不是占位符、列表页、垃圾广告或明显重复拼接内容；
3. 至少有足够的信息让用户理解活动内容，并能找到报名或活动详情；
4. 字段不完整本身不等于不通过，只在内容明显无效、错误或不可用时拒绝。

赛事数据：
{event_json}

只返回 JSON：
{{"approved": true, "reason": "简短原因", "confidence": 0.95}}
"""


CLEANING_PROMPT = """你是赛事内容编辑。请在不改变事实含义的前提下，清洗下面这条已通过质量筛选的赛事数据，让用户更容易阅读。

清洗目标：
1. 名称去掉网站标题、平台宣传语、重复后缀和无关营销文案，但必须保留赛事官方名称；
2. 摘要控制在 200 字以内，准确说明赛事主题、参赛对象和核心信息；
3. 描述删除导航栏、新闻推荐、课程广告、保研考研等无关抓取内容，去重并整理成清晰段落；
4. 对当前缺失的事实字段，只能在现有字段或 raw_data 中有明确原文依据时补充，否则返回 null；
5. 不得编造、推测或改写日期、金额、奖项、规则、主办方、地点、链接等事实；不得改变赛事真实含义；
6. 不得修改 id、slug、source_url、source_platform、raw_data、状态、计数等系统字段。

赛事数据：
{event_json}

只返回 JSON，字段结构如下：
{{
  "name": "清洗后的官方赛事名称",
  "summary": "清洗后的简洁摘要",
  "description": "清洗后的赛事介绍，使用纯文本自然分段，不要输出 Markdown 或 HTML",
  "missing_fields": {{
    "registration_start": null,
    "registration_end": null,
    "event_start": null,
    "event_end": null,
    "location": null,
    "country": null,
    "city": null,
    "organizer": null,
    "prize_pool": null,
    "registration_url": null,
    "cover_image": null,
    "track_tags": null,
    "tech_tags": null,
    "sponsors": null
  }}
}}
"""


class ScreeningResponseError(ValueError):
    """Raised when the model response does not contain a valid decision."""


class CleaningResponseError(ValueError):
    """Raised when the model response does not contain a cleaning result."""


class QualityScreeningClient:
    """Anthropic Messages-compatible client for the configured screening model."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = settings.LLM_API_KEY if api_key is None else api_key
        self.base_url = (
            base_url or settings.LLM_SCREENING_API_BASE_URL
        ).rstrip("/")
        self.model = model or settings.LLM_SCREENING_MODEL

    async def evaluate(self, event: dict[str, Any]) -> bool | None:
        """Return a display decision, or None when the event should be retried."""
        if not all((self.api_key, self.base_url, self.model)):
            logger.warning(
                "[Screening] 筛选失败：id=%s，名称=%s，稍后重试，原因=API 配置不完整",
                event.get("id"),
                event.get("name"),
            )
            return None

        event_json = json.dumps(event, ensure_ascii=False, default=str)
        if len(event_json) > 12_000:
            event_json = event_json[:12_000] + "...(truncated)"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "max_tokens": 1024,
                        "messages": [
                            {
                                "role": "user",
                                "content": SCREENING_PROMPT.format(event_json=event_json),
                            }
                        ],
                    },
                )
                response.raise_for_status()
                response_payload = response.json()
                content_blocks = response_payload["content"]
                if not isinstance(content_blocks, list):
                    raise ScreeningResponseError("模型响应 content 必须是数组")
                content = "".join(
                    block.get("text", "")
                    for block in content_blocks
                    if isinstance(block, dict) and block.get("type") == "text"
                )

                if not content and response_payload.get("stop_reason") == "max_tokens":
                    raise ScreeningResponseError(
                        "模型输出达到 max_tokens=1024，未生成文本结果"
                    )

            logger.info(
                "[Screening] 模型响应：id=%s，名称=%s，内容=%s",
                event.get("id"),
                event.get("name"),
                json.dumps(content, ensure_ascii=False),
            )
            parsed = _extract_json_from_text(content)
            if not isinstance(parsed, dict) or "approved" not in parsed:
                raise ScreeningResponseError("模型响应缺少 approved 字段")
            approved = parsed["approved"]
            if isinstance(approved, bool):
                return approved
            if isinstance(approved, str) and approved.lower() in {"true", "false"}:
                return approved.lower() == "true"
            raise ScreeningResponseError("approved 必须是布尔值")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "[Screening] 筛选失败：id=%s，名称=%s，稍后重试，原因=%s",
                event.get("id"),
                event.get("name"),
                exc,
            )
            return None


class EventCleaningClient:
    """Use the configured Messages-compatible model to improve presentation text."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = settings.LLM_API_KEY if api_key is None else api_key
        self.base_url = (
            base_url or settings.LLM_SCREENING_API_BASE_URL
        ).rstrip("/")
        self.model = model or settings.LLM_SCREENING_MODEL

    async def clean(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Return whitelisted cleaning suggestions, or None for a later retry."""
        if not all((self.api_key, self.base_url, self.model)):
            logger.warning(
                "[Cleaning] 清洗失败：id=%s，名称=%s，稍后重试，原因=API 配置不完整",
                event.get("id"),
                event.get("name"),
            )
            return None

        event_json = json.dumps(event, ensure_ascii=False, default=str)
        if len(event_json) > 30_000:
            event_json = event_json[:30_000] + "...(truncated)"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "max_tokens": 4096,
                        "messages": [
                            {
                                "role": "user",
                                "content": CLEANING_PROMPT.format(event_json=event_json),
                            }
                        ],
                    },
                )
                response.raise_for_status()
                response_payload = response.json()
                content_blocks = response_payload["content"]
                if not isinstance(content_blocks, list):
                    raise CleaningResponseError("模型响应 content 必须是数组")
                content = "".join(
                    block.get("text", "")
                    for block in content_blocks
                    if isinstance(block, dict) and block.get("type") == "text"
                )
                if not content and response_payload.get("stop_reason") == "max_tokens":
                    raise CleaningResponseError(
                        "模型输出达到 max_tokens=4096，未生成文本结果"
                    )

            logger.info(
                "[Cleaning] 模型响应：id=%s，名称=%s，内容=%s",
                event.get("id"),
                event.get("name"),
                json.dumps(content, ensure_ascii=False),
            )
            parsed = _extract_json_from_text(content)
            if not isinstance(parsed, dict):
                raise CleaningResponseError("模型响应不是 JSON 对象")
            if not any(
                key in parsed
                for key in ("name", "summary", "description", "missing_fields")
            ):
                raise CleaningResponseError("模型响应缺少清洗字段")
            return parsed
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "[Cleaning] 清洗失败：id=%s，名称=%s，稍后重试，原因=%s",
                event.get("id"),
                event.get("name"),
                exc,
            )
            return None


def _event_payload(event: Hackathon) -> dict[str, Any]:
    """Build the bounded, auditable input sent to the screening model."""
    return {
        "id": event.id,
        "name": event.name,
        "description": event.description,
        "summary": event.summary,
        "event_start": event.event_start,
        "event_end": event.event_end,
        "location": event.location,
        "source_url": event.source_url,
        "source_platform": event.source_platform,
        "registration_url": event.registration_url,
        "organizer": event.organizer,
        "raw_data": event.raw_data,
    }


def _cleaning_payload(event: Hackathon) -> dict[str, Any]:
    """Include presentation fields, missing factual fields and original evidence."""
    return {
        "id": event.id,
        "name": event.name,
        "summary": event.summary,
        "description": event.description,
        "registration_start": event.registration_start,
        "registration_end": event.registration_end,
        "event_start": event.event_start,
        "event_end": event.event_end,
        "track_tags": event.track_tags,
        "tech_tags": event.tech_tags,
        "prize_pool": event.prize_pool,
        "location": event.location,
        "country": event.country,
        "city": event.city,
        "registration_url": event.registration_url,
        "organizer": event.organizer,
        "sponsors": event.sponsors,
        "cover_image": event.cover_image,
        "source_url": event.source_url,
        "source_platform": event.source_platform,
        "raw_data": event.raw_data,
    }


def _clean_string(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_length].strip()


def _clean_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned = []
    for item in value:
        normalized = _clean_string(item, 100)
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned[:20] or None


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _build_cleaning_updates(
    event: Hackathon,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Apply only presentation rewrites and evidence-backed missing facts."""
    updates: dict[str, Any] = {}
    prose_limits = {"name": 500, "summary": 500, "description": 20_000}
    for field, limit in prose_limits.items():
        value = _clean_string(result.get(field), limit)
        if value is not None:
            updates[field] = value

    missing = result.get("missing_fields")
    if not isinstance(missing, dict):
        missing = {}

    text_limits = {
        "location": 300,
        "country": 100,
        "city": 100,
        "organizer": 300,
        "prize_pool": 200,
        "registration_url": 1000,
        "cover_image": 1000,
    }
    for field, limit in text_limits.items():
        if getattr(event, field, None):
            continue
        value = _clean_string(missing.get(field), limit)
        if value is None:
            continue
        if field in {"registration_url", "cover_image"} and not _is_http_url(value):
            continue
        updates[field] = value

    for field in ("track_tags", "tech_tags", "sponsors"):
        if getattr(event, field, None):
            continue
        value = _clean_string_list(missing.get(field))
        if value:
            updates[field] = value

    for field in (
        "registration_start",
        "registration_end",
        "event_start",
        "event_end",
    ):
        if getattr(event, field, None) is not None:
            continue
        value = parse_date(missing.get(field))
        if value is not None:
            updates[field] = value

    for start_field, end_field in (
        ("registration_start", "registration_end"),
        ("event_start", "event_end"),
    ):
        start = updates.get(start_field, getattr(event, start_field, None))
        end = updates.get(end_field, getattr(event, end_field, None))
        if start is not None and end is not None and start > end:
            updates.pop(start_field, None)
            updates.pop(end_field, None)

    return updates


class HackathonScreeningWorker:
    """Own the durable screening-then-cleaning pipeline."""

    def __init__(
        self,
        client: QualityScreeningClient | None = None,
        cleaning_client: EventCleaningClient | None = None,
    ) -> None:
        self.client = client or QualityScreeningClient()
        self.cleaning_client = cleaning_client or EventCleaningClient()
        self._queue: asyncio.Queue[int] | None = None
        self._queued_ids: set[int] = set()
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def is_running(self) -> bool:
        return bool(self._tasks) and all(not task.done() for task in self._tasks)

    async def start(self) -> None:
        if self.is_running:
            return
        self._queue = asyncio.Queue()
        self._queued_ids.clear()
        worker_count = max(1, settings.LLM_SCREENING_WORKERS)
        self._tasks = [
            asyncio.create_task(self._run(index), name=f"hackathon-screening-{index}")
            for index in range(worker_count)
        ]
        logger.info("[Screening] 已启动 %s 个异步 worker", worker_count)

    async def stop(self) -> None:
        tasks = list(self._tasks)
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks)
        self._queued_ids.clear()
        self._queue = None
        logger.info("[Screening] worker 已停止")

    def enqueue(self, event_ids: Iterable[int]) -> int:
        """Enqueue unique persisted IDs without blocking the crawler transaction."""
        if self._queue is None or not self.is_running:
            logger.warning("[Screening] worker 未启动，等待定时补扫待筛选/待清洗赛事")
            return 0

        enqueued = 0
        for event_id in event_ids:
            normalized_id = int(event_id)
            if normalized_id in self._queued_ids:
                continue
            self._queued_ids.add(normalized_id)
            self._queue.put_nowait(normalized_id)
            enqueued += 1
        return enqueued

    async def scan_pending(self) -> int:
        """Recover rows waiting for either screening or post-screen cleaning."""
        batch_size = max(1, settings.LLM_SCREENING_BATCH_SIZE)
        last_id = 0
        screening_count = 0
        cleaning_count = 0
        enqueued = 0
        async with async_session_factory() as session:
            while True:
                result = await session.execute(
                    select(Hackathon.id, Hackathon.display_status)
                    .where(
                        or_(
                            Hackathon.display_status == HackathonDisplayStatus.PENDING,
                            and_(
                                Hackathon.display_status
                                == HackathonDisplayStatus.APPROVED,
                                Hackathon.is_cleaned.is_(False),
                            ),
                        ),
                        Hackathon.id > last_id,
                    )
                    .order_by(Hackathon.id.asc())
                    .limit(batch_size)
                )
                rows = list(result.all())
                if not rows:
                    break
                event_ids = [row[0] for row in rows]
                screening_count += sum(
                    1 for _, status in rows
                    if status == HackathonDisplayStatus.PENDING
                )
                cleaning_count += sum(
                    1 for _, status in rows
                    if status == HackathonDisplayStatus.APPROVED
                )
                enqueued += self.enqueue(event_ids)
                last_id = event_ids[-1]
                if len(event_ids) < batch_size:
                    break
        logger.info(
            "[Screening] 补扫待筛选=%s，待清洗=%s，新增入队=%s",
            screening_count,
            cleaning_count,
            enqueued,
        )
        return enqueued

    async def _run(self, worker_index: int) -> None:
        assert self._queue is not None
        while True:
            event_id = await self._queue.get()
            try:
                await self._process_event(event_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[Screening] worker=%s 处理赛事 %s 异常", worker_index, event_id)
            finally:
                self._queued_ids.discard(event_id)
                self._queue.task_done()

    async def _process_event(self, event_id: int) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon.display_status, Hackathon.is_cleaned).where(
                    Hackathon.id == event_id
                )
            )
            state = result.one_or_none()
        if state is None:
            return
        display_status, is_cleaned = state
        if display_status == HackathonDisplayStatus.PENDING:
            await self._screen_event(event_id)
        elif display_status == HackathonDisplayStatus.APPROVED and not is_cleaned:
            await self._clean_event(event_id)

    async def _screen_event(self, event_id: int) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon).where(
                    Hackathon.id == event_id,
                    Hackathon.display_status == HackathonDisplayStatus.PENDING,
                )
            )
            event = result.scalar_one_or_none()
            if event is None:
                return
            original_status = event.display_status
            event_name = event.name
            payload = _event_payload(event)

        logger.info("[Screening] 开始筛选：id=%s，名称=%s", event_id, event_name)
        approved = await self.client.evaluate(payload)
        if approved is None:
            return

        new_status = (
            HackathonDisplayStatus.APPROVED
            if approved
            else HackathonDisplayStatus.REJECTED
        )
        async with async_session_factory() as session:
            await session.execute(
                update(Hackathon)
                .where(
                    Hackathon.id == event_id,
                    Hackathon.display_status == original_status,
                )
                .values(display_status=new_status)
            )
            await session.commit()
        result_text = "通过" if approved else "未通过"
        logger.info(
            "[Screening] 筛选完成：id=%s，名称=%s，结果=%s",
            event_id,
            event_name,
            result_text,
        )
        if approved:
            await self._clean_event(event_id)

    async def _clean_event(self, event_id: int) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon).where(
                    Hackathon.id == event_id,
                    Hackathon.display_status == HackathonDisplayStatus.APPROVED,
                    Hackathon.is_cleaned.is_(False),
                )
            )
            event = result.scalar_one_or_none()
            if event is None:
                return
            event_name = event.name
            payload = _cleaning_payload(event)

        logger.info("[Cleaning] 开始清洗：id=%s，名称=%s", event_id, event_name)
        cleaned = await self.cleaning_client.clean(payload)
        if cleaned is None:
            return

        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon).where(
                    Hackathon.id == event_id,
                    Hackathon.display_status == HackathonDisplayStatus.APPROVED,
                    Hackathon.is_cleaned.is_(False),
                )
            )
            event = result.scalar_one_or_none()
            if event is None:
                return
            updates = _build_cleaning_updates(event, cleaned)
            updates["is_cleaned"] = True
            await session.execute(
                update(Hackathon)
                .where(
                    Hackathon.id == event_id,
                    Hackathon.display_status == HackathonDisplayStatus.APPROVED,
                    Hackathon.is_cleaned.is_(False),
                )
                .values(**updates)
            )
            await session.commit()

        changed_fields = sorted(field for field in updates if field != "is_cleaned")
        logger.info(
            "[Cleaning] 清洗完成：id=%s，名称=%s，更新字段=%s",
            event_id,
            event_name,
            ",".join(changed_fields) if changed_fields else "无内容变更",
        )


screening_worker = HackathonScreeningWorker()
