"""Asynchronous LLM quality screening for persisted hackathons.

The database PENDING state is the durable source of truth.  The in-process
queue provides low-latency screening after a crawl, while the periodic scan
recovers work after process restarts or transient API failures.
"""

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any, Iterable

import httpx
from sqlalchemy import select, update

from app.config import settings
from app.crawler.llm_processor import _extract_json_from_text
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


class ScreeningResponseError(ValueError):
    """Raised when the model response does not contain a valid decision."""


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


class HackathonScreeningWorker:
    """Own an asyncio queue and update the three-state display decision."""

    def __init__(self, client: QualityScreeningClient | None = None) -> None:
        self.client = client or QualityScreeningClient()
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
            logger.warning("[Screening] worker 未启动，等待定时补扫 pending 赛事")
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
        """Find durable pending rows and enqueue them for screening."""
        batch_size = max(1, settings.LLM_SCREENING_BATCH_SIZE)
        last_id = 0
        pending_count = 0
        enqueued = 0
        async with async_session_factory() as session:
            while True:
                result = await session.execute(
                    select(Hackathon.id)
                    .where(
                        Hackathon.display_status == HackathonDisplayStatus.PENDING,
                        Hackathon.id > last_id,
                    )
                    .order_by(Hackathon.id.asc())
                    .limit(batch_size)
                )
                event_ids = list(result.scalars().all())
                if not event_ids:
                    break
                pending_count += len(event_ids)
                enqueued += self.enqueue(event_ids)
                last_id = event_ids[-1]
                if len(event_ids) < batch_size:
                    break
        logger.info(
            "[Screening] 补扫 pending=%s，新增入队=%s", pending_count, enqueued
        )
        return enqueued

    async def _run(self, worker_index: int) -> None:
        assert self._queue is not None
        while True:
            event_id = await self._queue.get()
            try:
                await self._screen_event(event_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[Screening] worker=%s 处理赛事 %s 异常", worker_index, event_id)
            finally:
                self._queued_ids.discard(event_id)
                self._queue.task_done()

    async def _screen_event(self, event_id: int) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Hackathon).where(Hackathon.id == event_id)
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


screening_worker = HackathonScreeningWorker()
