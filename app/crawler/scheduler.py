"""
爬虫调度器 — 定时抓取、确定性映射、持久化并投递异步筛选任务
对应架构图中的「自动化爬虫引擎 (D1)」

特性：
- 跨平台去重（基于名称相似度 + URL 规范化）
- 运行历史记录
- 统计指标
- 失败告警钩子
"""

import asyncio
import json
import logging
import re
from dataclasses import asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from app.config import settings
from app.crawler.base import CrawlResult
from app.crawler.dorahacks import dorahacks_crawler
from app.crawler.devpost import devpost_crawler
from app.crawler.mlh import mlh_crawler
from app.crawler.eventbrite import eventbrite_crawler
from app.crawler.saikr import saikr_crawler
from app.crawler.tianchi import tianchi_crawler
from app.crawler.huodongxing import huodongxing_crawler
from app.crawler.ethglobal import ethglobal_crawler
from app.crawler.hackathon_com import hackathon_com_crawler
from app.crawler.itch_jams import itch_jams_crawler
from app.crawler.llm_processor import StandardizedHackathon
from app.crawler.mapper import crawl_result_to_standardized
from app.crawler.persistence import persist_batch, PersistenceResult
from app.crawler.screening_worker import screening_worker
from app.db import async_session_factory

logger = logging.getLogger(__name__)

# 爬虫注册表
CRAWLER_REGISTRY = {
    "dorahacks": dorahacks_crawler,
    "devpost": devpost_crawler,
    "mlh": mlh_crawler,
    "eventbrite": eventbrite_crawler,
    "saikr": saikr_crawler,
    "tianchi": tianchi_crawler,
    "huodongxing": huodongxing_crawler,
    "ethglobal": ethglobal_crawler,
    "hackathon_com": hackathon_com_crawler,
    "itch_jams": itch_jams_crawler,
}

# 爬取频率
CRAWL_SCHEDULE = {
    "dorahacks": "每日 03:00",
    "devpost": "每日 02:00",
    "mlh": "每日 02:30",
    "eventbrite": "每6小时",
    "saikr": "每日 04:30",
    "tianchi": "每日 05:00",
    "huodongxing": "每6小时",
    "ethglobal": "每日 05:30",
    "hackathon_com": "每日 06:00",
    "itch_jams": "每日 06:30",
}

# 去重相似度阈值（高于此值视为重复）
DEDUP_SIMILARITY_THRESHOLD = 0.85

ProgressCallback = Callable[..., None]


class CrawlerBusyError(RuntimeError):
    """Raised when a scheduled or manual crawler already owns a target."""


def _report_progress(
    callback: ProgressCallback | None,
    *,
    progress: int,
    phase: str,
    message: str,
    current_platform: str | None = None,
    completed_platforms: int | None = None,
    total_platforms: int | None = None,
) -> None:
    if callback is None:
        return
    callback(
        progress=progress,
        phase=phase,
        message=message,
        current_platform=current_platform,
        completed_platforms=completed_platforms,
        total_platforms=total_platforms,
    )


def _normalize_name(name: str) -> str:
    """规范化活动名称用于比较：小写、去标点、去空格"""
    if not name:
        return ""
    name = name.lower()
    # 去除常见后缀/前缀词
    name = re.sub(r"\b(hackathon|黑客松|黑客马拉松|2026|2025)\b", "", name, flags=re.IGNORECASE)
    # 去除非字母数字（保留中文）
    name = re.sub(r"[^\w\u4e00-\u9fff]", "", name, flags=re.UNICODE)
    return name


def _name_similarity(a: str, b: str) -> float:
    """计算两个名称的相似度（0-1）"""
    na = _normalize_name(a)
    nb = _normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _normalize_url(url: str) -> str:
    """规范化 URL：去 query、fragment、尾部斜杠"""
    if not url:
        return ""
    # 去 fragment
    url = url.split("#")[0]
    # 去 query
    url = url.split("?")[0]
    # 去尾部斜杠
    url = url.rstrip("/")
    return url.lower()


def deduplicate(
    items: list[StandardizedHackathon],
    threshold: float = DEDUP_SIMILARITY_THRESHOLD,
) -> tuple[list[StandardizedHackathon], list[dict]]:
    """跨平台去重

    Returns:
        (去重后列表, 被合并的重复项记录)
    """
    seen: list[StandardizedHackathon] = []
    merged_records: list[dict] = []

    for item in items:
        is_dup = False
        for idx, existing in enumerate(seen):
            # URL 完全相同（规范化后）→ 重复
            if _normalize_url(item.source_url) and _normalize_url(item.source_url) == _normalize_url(existing.source_url):
                is_dup = True
                # 合并字段：补充 existing 中缺失的字段
                _merge_into(existing, item)
                merged_records.append({
                    "kept": existing.source_platform,
                    "kept_url": existing.source_url,
                    "dropped": item.source_platform,
                    "dropped_url": item.source_url,
                    "reason": "url_match",
                    "similarity": 1.0,
                })
                break

            # 名称相似度高 → 重复
            sim = _name_similarity(item.name, existing.name)
            if sim >= threshold:
                is_dup = True
                _merge_into(existing, item)
                merged_records.append({
                    "kept": existing.source_platform,
                    "kept_url": existing.source_url,
                    "dropped": item.source_platform,
                    "dropped_url": item.source_url,
                    "reason": "name_similarity",
                    "similarity": round(sim, 3),
                })
                break

        if not is_dup:
            seen.append(item)

    return seen, merged_records


def _merge_into(target: StandardizedHackathon, source: StandardizedHackathon):
    """将 source 的字段合并到 target（仅补充 target 中缺失的字段）"""
    # 收集所有来源平台
    if source.source_platform and source.source_platform not in (target.source_platform or ""):
        existing_platforms = set((target.raw_data.get("_source_platforms") or [target.source_platform]))
        existing_platforms.add(source.source_platform)
        target.raw_data["_source_platforms"] = sorted(existing_platforms)

    # 补充空字段
    for field_name in ["summary", "registration_start", "registration_end",
                       "event_start", "event_end", "prize_pool", "prize_pool_usd",
                       "location", "country", "city", "organizer", "rules"]:
        if not getattr(target, field_name, None):
            val = getattr(source, field_name, None)
            if val:
                setattr(target, field_name, val)

    # 合并列表字段（去重）
    for field_name in ["track_tags", "tech_tags", "sponsors", "requirements"]:
        existing = getattr(target, field_name, []) or []
        new = getattr(source, field_name, []) or []
        merged = list(dict.fromkeys(existing + new))
        setattr(target, field_name, merged)

    # 取较高置信度
    if source.llm_confidence > target.llm_confidence:
        target.llm_confidence = source.llm_confidence


class CrawlerScheduler:
    """爬虫调度器"""

    def __init__(self):
        # 运行历史：最近 N 次运行记录
        self._history: list[dict] = []
        self._max_history = 50
        # 累计统计
        self._stats = {
            "total_runs": 0,
            "success_runs": 0,
            "error_runs": 0,
            "total_raw": 0,
            "total_cleaned": 0,
            "total_deduplicated": 0,
        }
        # 输出目录
        self._output_dir = Path(settings.CRAWLER_OUTPUT_DIR)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Scheduled and manual runs share these locks.
        self._platform_locks: dict[str, asyncio.Lock] = {}
        self._all_lock = asyncio.Lock()

    def _platform_lock(self, platform: str) -> asyncio.Lock:
        return self._platform_locks.setdefault(platform, asyncio.Lock())

    def is_platform_running(self, platform: str) -> bool:
        return self._all_lock.locked() or self._platform_lock(platform).locked()

    def any_platform_running(self) -> bool:
        return any(lock.locked() for lock in self._platform_locks.values())

    def is_all_running(self) -> bool:
        return self._all_lock.locked()

    async def run_platform(
        self,
        platform: str,
        save_json: bool = True,
        persist: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        """运行单个平台的抓取、持久化与异步筛选投递流水线

        Args:
            platform: 平台名称
            save_json: 是否保存为 JSON 文件
            persist: 是否持久化到数据库
        """
        crawler = CRAWLER_REGISTRY.get(platform)
        if crawler is None:
            return {"platform": platform, "status": "unknown", "count": 0}

        lock = self._platform_lock(platform)
        if self._all_lock.locked() or lock.locked():
            raise CrawlerBusyError(f"平台 {platform} 正在运行")
        await lock.acquire()

        logger.info(f"[Scheduler] 开始爬取平台: {platform}")
        start_time = datetime.now()

        try:
            # 1. 爬取原始数据
            _report_progress(
                progress_callback,
                progress=15,
                phase="fetching",
                message=f"正在抓取 {platform}",
                current_platform=platform,
            )
            max_items = settings.CRAWLER_MAX_ITEMS_PER_PLATFORM or None
            raw_results: list[CrawlResult] = await crawler.run(max_items=max_items)

            # 2. 仅做确定性字段映射。LLM 筛选与清洗由入库后的 worker 异步执行。
            standardized = [crawl_result_to_standardized(item) for item in raw_results]

            # 3. 持久化到数据库（可选）
            persistence_result = None
            if persist and standardized:
                _report_progress(
                    progress_callback,
                    progress=80,
                    phase="persisting",
                    message=f"正在写入 {platform}",
                    current_platform=platform,
                )
                try:
                    async with async_session_factory() as session:
                        persistence_result = await persist_batch(session, standardized)
                    screening_worker.enqueue(persistence_result.event_ids)
                    logger.info(f"[Scheduler] {platform} 持久化: {persistence_result}")
                except Exception as e:
                    logger.error(f"[Scheduler] {platform} 持久化失败: {e}")
                    persistence_result = PersistenceResult()
                    persistence_result.errors.append(f"db_persistence_failed: {e}")

            # 4. 保存为 JSON
            _report_progress(
                progress_callback,
                progress=95,
                phase="saving",
                message=f"正在完成 {platform}",
                current_platform=platform,
            )
            if save_json and standardized:
                self._save_to_json(platform, standardized)

            elapsed = (datetime.now() - start_time).total_seconds()
            success_count = sum(1 for r in raw_results if r.success)
            result = {
                "platform": platform,
                "status": "success",
                "raw_count": len(raw_results),
                "success_count": success_count,
                "failed_count": len(raw_results) - success_count,
                "mapped_count": len(standardized),
                "cleaned_count": len(standardized),
                "elapsed_seconds": round(elapsed, 1),
                "schedule": CRAWL_SCHEDULE.get(platform, "按需"),
                "timestamp": start_time.isoformat(),
                "persistence": persistence_result.to_dict() if persistence_result else None,
            }
            self._record_run(result)
            _report_progress(
                progress_callback,
                progress=100,
                phase="completed",
                message=f"{platform} 爬取完成",
                current_platform=platform,
                completed_platforms=1,
                total_platforms=1,
            )
            return result
        except Exception as e:
            logger.error(f"[Scheduler] 平台 {platform} 爬取失败: {e}")
            elapsed = (datetime.now() - start_time).total_seconds()
            result = {
                "platform": platform,
                "status": "error",
                "error": str(e),
                "elapsed_seconds": round(elapsed, 1),
                "timestamp": start_time.isoformat(),
            }
            self._record_run(result)
            await self._alert_failure(platform, str(e))
            return result
        finally:
            lock.release()

    async def run_all_with_dedup(
        self,
        save_json: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        """运行所有平台抓取 + 跨平台去重

        爬虫任务不调用 LLM：抓取 → 本地映射 → 去重 → 入库 → 投递筛选队列。
        """
        if self._all_lock.locked():
            raise CrawlerBusyError("全量爬虫任务正在运行")
        await self._all_lock.acquire()
        try:
            if self.any_platform_running():
                raise CrawlerBusyError("已有单平台爬虫任务正在运行")
            return await self._run_all_with_dedup_locked(
                save_json=save_json,
                progress_callback=progress_callback,
            )
        finally:
            self._all_lock.release()

    async def _run_all_with_dedup_locked(
        self,
        *,
        save_json: bool,
        progress_callback: ProgressCallback | None,
    ) -> dict:
        logger.info(f"[Scheduler] 全量爬取（含去重）开始 {datetime.now()}")
        start_time = datetime.now()
        preferred_order = [
            "dorahacks",
            "saikr",
            "tianchi",
            "devpost",
            "mlh",
            "eventbrite",
            "huodongxing",
            "ethglobal",
            "hackathon_com",
            "itch_jams",
        ]
        priority_order = [name for name in preferred_order if name in CRAWLER_REGISTRY]
        priority_order.extend(name for name in CRAWLER_REGISTRY if name not in priority_order)

        all_standardized: list[StandardizedHackathon] = []
        platform_results: list[dict] = []
        total_platforms = len(priority_order)

        for index, platform in enumerate(priority_order):
            crawler = CRAWLER_REGISTRY.get(platform)
            if crawler is None:
                continue

            platform_start = datetime.now()
            platform_lock = self._platform_lock(platform)
            await platform_lock.acquire()
            try:
                slice_start = 5 + int((index / max(total_platforms, 1)) * 80)
                _report_progress(
                    progress_callback,
                    progress=slice_start,
                    phase="fetching",
                    message=f"正在抓取 {platform}",
                    current_platform=platform,
                    completed_platforms=index,
                    total_platforms=total_platforms,
                )
                max_items = settings.CRAWLER_MAX_ITEMS_PER_PLATFORM or None
                raw_results = await crawler.run(max_items=max_items)
                # Crawler tasks must not wait for LLM calls. Persist source data
                # first, then enqueue the stored rows for asynchronous screening.
                standardized = [crawl_result_to_standardized(item) for item in raw_results]
                all_standardized.extend(standardized)

                elapsed = (datetime.now() - platform_start).total_seconds()
                result = {
                    "platform": platform,
                    "status": "success",
                    "raw_count": len(raw_results),
                    "mapped_count": len(standardized),
                    "cleaned_count": len(standardized),
                    "elapsed_seconds": round(elapsed, 1),
                }
            except Exception as e:
                logger.error(f"[Scheduler] 平台 {platform} 失败: {e}")
                result = {
                    "platform": platform,
                    "status": "error",
                    "error": str(e),
                    "elapsed_seconds": round((datetime.now() - platform_start).total_seconds(), 1),
                }
                await self._alert_failure(platform, str(e))
            finally:
                platform_lock.release()

            platform_results.append(result)
            self._record_run(result)
            completed_progress = 5 + int(((index + 1) / max(total_platforms, 1)) * 80)
            _report_progress(
                progress_callback,
                progress=completed_progress,
                phase="fetching",
                message=f"已完成 {platform}",
                current_platform=platform,
                completed_platforms=index + 1,
                total_platforms=total_platforms,
            )
            await asyncio.sleep(1)

        # 跨平台去重
        _report_progress(
            progress_callback,
            progress=88,
            phase="deduplicating",
            message="正在跨平台去重",
            completed_platforms=total_platforms,
            total_platforms=total_platforms,
        )
        deduped, merged_records = deduplicate(all_standardized)
        logger.info(
            f"[Scheduler] 去重: {len(all_standardized)} → {len(deduped)} "
            f"(合并 {len(merged_records)} 条重复)"
        )

        # 持久化到数据库
        _report_progress(
            progress_callback,
            progress=94,
            phase="persisting",
            message="正在写入数据库",
            completed_platforms=total_platforms,
            total_platforms=total_platforms,
        )
        persistence_result: PersistenceResult | None = None
        try:
            async with async_session_factory() as session:
                persistence_result = await persist_batch(session, deduped)
            screening_worker.enqueue(persistence_result.event_ids)
            logger.info(f"[Scheduler] 持久化完成: {persistence_result}")
        except Exception as e:
            logger.error(f"[Scheduler] 持久化失败（不影响 JSON 保存）: {e}")
            persistence_result = PersistenceResult()
            persistence_result.errors.append(f"db_persistence_failed: {e}")

        _report_progress(
            progress_callback,
            progress=98,
            phase="saving",
            message="正在保存任务结果",
            completed_platforms=total_platforms,
            total_platforms=total_platforms,
        )
        if save_json and deduped:
            self._save_to_json("all_deduped", deduped)
        if save_json and merged_records:
            self._save_dedup_log(merged_records)

        total_elapsed = (datetime.now() - start_time).total_seconds()
        result = {
            "platforms": platform_results,
            "dedup": {
                "before": len(all_standardized),
                "after": len(deduped),
                "merged": len(merged_records),
            },
            "persistence": persistence_result.to_dict() if persistence_result else None,
            "total_elapsed_seconds": round(total_elapsed, 1),
            "summary": self._build_summary(platform_results),
        }
        _report_progress(
            progress_callback,
            progress=100,
            phase="completed",
            message="全量爬虫任务已完成",
            completed_platforms=total_platforms,
            total_platforms=total_platforms,
        )
        return result

    def _build_summary(self, results: list[dict]) -> dict:
        """构建运行汇总"""
        total_raw = sum(r.get("raw_count", 0) for r in results)
        total_cleaned = sum(r.get("cleaned_count", 0) for r in results)
        success_platforms = sum(1 for r in results if r.get("status") == "success")
        error_platforms = sum(1 for r in results if r.get("status") == "error")
        return {
            "total_platforms": len(results),
            "success_platforms": success_platforms,
            "error_platforms": error_platforms,
            "total_raw": total_raw,
            "total_cleaned": total_cleaned,
        }

    def _record_run(self, result: dict):
        """记录运行历史，更新统计"""
        self._history.append(result)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        self._stats["total_runs"] += 1
        if result.get("status") == "success":
            self._stats["success_runs"] += 1
            self._stats["total_raw"] += result.get("raw_count", 0)
            self._stats["total_cleaned"] += result.get("cleaned_count", 0)
        else:
            self._stats["error_runs"] += 1

    async def _alert_failure(self, platform: str, error: str):
        """失败告警钩子（可扩展为邮件/Slack 通知）"""
        logger.warning(f"[Alert] 平台 {platform} 失败: {error}")
        # TODO: 接入 EDM 服务或 Slack webhook

    def _save_to_json(self, platform: str, items: list[StandardizedHackathon]):
        """保存单平台结果为 JSON"""
        filename = self._output_dir / f"crawl_{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        data = [asdict(item) for item in items]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"[Scheduler] 已保存 {len(items)} 条到 {filename}")

    def _save_combined_json(self, results: list[dict]):
        """保存汇总结果"""
        filename = self._output_dir / f"crawl_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"[Scheduler] 汇总结果已保存到 {filename}")

    def _save_dedup_log(self, merged_records: list[dict]):
        """保存去重日志"""
        filename = self._output_dir / f"dedup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(merged_records, f, ensure_ascii=False, indent=2)
        logger.info(f"[Scheduler] 去重日志已保存到 {filename}")

    def get_status(self) -> dict:
        """获取爬虫系统状态"""
        return {
            "platforms": list(CRAWLER_REGISTRY.keys()),
            "schedules": CRAWL_SCHEDULE,
            "llm_model": settings.LLM_MODEL,
            "status": "running" if CRAWLER_REGISTRY else "idle",
            "stats": self._stats,
            "recent_runs": self._history[-10:],
            "output_dir": str(self._output_dir),
        }

    def get_history(self, limit: int = 20) -> list[dict]:
        """获取运行历史"""
        return self._history[-limit:]


# 全局调度器实例
scheduler = CrawlerScheduler()
