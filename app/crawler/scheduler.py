"""
爬虫调度器 — 对应架构图中的「自动化爬虫引擎 (D1)」
负责定时调度所有平台爬虫，并驱动 LLM 数据清洗流水线

⚠️ Mock 实现 — 不执行真实定时任务
"""

import asyncio
import logging

from app.crawler.base import CrawlResult
from app.crawler.devpost import devpost_crawler
from app.crawler.mlh import mlh_crawler
from app.crawler.eventbrite import eventbrite_crawler
from app.crawler.dorahacks import dorahacks_crawler
from app.crawler.llm_processor import LLMProcessor, StandardizedHackathon

logger = logging.getLogger(__name__)

# 爬虫注册表
CRAWLER_REGISTRY = {
    "devpost": devpost_crawler,
    "mlh": mlh_crawler,
    "eventbrite": eventbrite_crawler,
    "dorahacks": dorahacks_crawler,
    # 后续可扩展:
    # "saikr": saikr_crawler,
    # "tianchi": tianchi_crawler,
    # "huodongxing": huodongxing_crawler,
    # "huaweicloud": huaweicloud_crawler,
}

# 爬取频率（对应调研报告建议）
CRAWL_SCHEDULE = {
    "devpost": "每日 02:00",
    "mlh": "每日 02:30",
    "eventbrite": "每6小时",
    "dorahacks": "每日 03:00",
    "saikr": "每日 04:00",
    "tianchi": "每日 04:30",
    "huodongxing": "每6小时",
}


class CrawlerScheduler:
    """
    爬虫调度器

    职责：
    1. 按定时计划触发各平台爬虫
    2. 收集爬取结果 → 送入 LLM 清洗流水线
    3. 将标准化数据写入数据库
    4. 记录爬取日志和异常

    Mock 实现：仅跑通流水线，不实际写入数据库
    """

    def __init__(self, llm_processor: LLMProcessor | None = None):
        self.llm_processor = llm_processor or LLMProcessor()

    async def run_platform(self, platform: str) -> dict:
        """运行单个平台的爬取 + 清洗流水线"""
        crawler = CRAWLER_REGISTRY.get(platform)
        if crawler is None:
            return {"platform": platform, "status": "unknown", "count": 0}

        logger.info(f"[Scheduler] 开始爬取平台: {platform}")

        try:
            # 1. 爬取原始数据
            raw_results: list[CrawlResult] = await crawler.run()

            # 2. LLM 清洗
            standardized: list[StandardizedHackathon] = await self.llm_processor.process_batch(raw_results)

            # 3. 写入数据库（Mock: 仅记录日志）
            await self._save_to_db(standardized)

            return {
                "platform": platform,
                "status": "success",
                "raw_count": len(raw_results),
                "cleaned_count": len(standardized),
                "schedule": CRAWL_SCHEDULE.get(platform, "按需"),
            }
        except Exception as e:
            logger.error(f"[Scheduler] 平台 {platform} 爬取失败: {e}")
            return {"platform": platform, "status": "error", "error": str(e)}

    async def run_all(self) -> list[dict]:
        """运行所有平台的爬取流水线（按优先级顺序）"""
        # 第一梯队：Devpost + MLH + Eventbrite
        # 第二梯队：DoraHacks
        priority_order = ["devpost", "mlh", "eventbrite", "dorahacks"]

        results = []
        for platform in priority_order:
            result = await self.run_platform(platform)
            results.append(result)
            # 平台间间隔
            await asyncio.sleep(1)

        return results

    async def _save_to_db(self, items: list[StandardizedHackathon]) -> None:
        """
        将标准化数据写入数据库

        Mock 实现：仅记录日志
        生产环境：批量 INSERT 到 hackathons 表
        """
        for item in items:
            logger.info(
                f"[DB] Mock 写入: {item.name} | "
                f"来源: {item.source_platform} | "
                f"置信度: {item.llm_confidence:.0%}"
            )

    def get_status(self) -> dict:
        """获取爬虫系统状态"""
        return {
            "platforms": list(CRAWLER_REGISTRY.keys()),
            "schedules": CRAWL_SCHEDULE,
            "llm_model": self.llm_processor.model,
            "status": "running" if CRAWLER_REGISTRY else "idle",
        }


# 全局调度器实例
scheduler = CrawlerScheduler()