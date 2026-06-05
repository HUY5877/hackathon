"""
爬虫调度器 — 定时调度所有平台爬虫，驱动 LLM 数据清洗流水线
对应架构图中的「自动化爬虫引擎 (D1)」
"""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime

from app.crawler.base import CrawlResult
from app.crawler.dorahacks import dorahacks_crawler
from app.crawler.competehub import competehub_crawler
from app.crawler.devpost import devpost_crawler
from app.crawler.mlh import mlh_crawler
from app.crawler.eventbrite import eventbrite_crawler
from app.crawler.saikr import saikr_crawler
from app.crawler.tianchi import tianchi_crawler
from app.crawler.huodongxing import huodongxing_crawler
from app.crawler.llm_processor import LLMProcessor, StandardizedHackathon

logger = logging.getLogger(__name__)

# 爬虫注册表
CRAWLER_REGISTRY = {
    "dorahacks": dorahacks_crawler,
    "competehub": competehub_crawler,
    "devpost": devpost_crawler,
    "mlh": mlh_crawler,
    "eventbrite": eventbrite_crawler,
    "saikr": saikr_crawler,
    "tianchi": tianchi_crawler,
    "huodongxing": huodongxing_crawler,
}

# 爬取频率
CRAWL_SCHEDULE = {
    "dorahacks": "每日 03:00",
    "competehub": "每日 04:00",
    "devpost": "每日 02:00",
    "mlh": "每日 02:30",
    "eventbrite": "每6小时",
    "saikr": "每日 04:30",
    "tianchi": "每日 05:00",
    "huodongxing": "每6小时",
}


class CrawlerScheduler:
    """爬虫调度器"""

    def __init__(self, llm_processor: LLMProcessor | None = None):
        self.llm_processor = llm_processor or LLMProcessor()

    async def run_platform(self, platform: str, save_json: bool = True) -> dict:
        """运行单个平台的爬取 + 清洗流水线"""
        crawler = CRAWLER_REGISTRY.get(platform)
        if crawler is None:
            return {"platform": platform, "status": "unknown", "count": 0}

        logger.info(f"[Scheduler] 开始爬取平台: {platform}")
        start_time = datetime.now()

        try:
            # 1. 爬取原始数据
            raw_results: list[CrawlResult] = await crawler.run()

            # 2. LLM 清洗
            standardized: list[StandardizedHackathon] = await self.llm_processor.process_batch(raw_results)

            # 3. 保存为 JSON（暂不入库）
            if save_json and standardized:
                self._save_to_json(platform, standardized)

            elapsed = (datetime.now() - start_time).total_seconds()
            return {
                "platform": platform,
                "status": "success",
                "raw_count": len(raw_results),
                "cleaned_count": len(standardized),
                "elapsed_seconds": round(elapsed, 1),
                "schedule": CRAWL_SCHEDULE.get(platform, "按需"),
            }
        except Exception as e:
            logger.error(f"[Scheduler] 平台 {platform} 爬取失败: {e}")
            return {"platform": platform, "status": "error", "error": str(e)}

    async def run_all(self, save_json: bool = True) -> list[dict]:
        """运行所有平台的爬取流水线"""
        logger.info(f"[Scheduler] 全量爬取开始 {datetime.now()}")
        priority_order = ["dorahacks", "competehub", "saikr", "tianchi", "devpost", "mlh", "eventbrite", "huodongxing"]

        results = []
        all_standardized = []

        for platform in priority_order:
            result = await self.run_platform(platform, save_json=False)
            results.append(result)
            await asyncio.sleep(1)

        # 合并所有平台结果保存为单个 JSON
        if save_json:
            self._save_combined_json(results)

        logger.info(f"[Scheduler] 全量爬取完成 {datetime.now()}")
        return results

    def _save_to_json(self, platform: str, items: list[StandardizedHackathon]):
        """保存单平台结果为 JSON"""
        filename = f"crawl_{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        data = [asdict(item) for item in items]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"[Scheduler] 已保存 {len(items)} 条到 {filename}")

    def _save_combined_json(self, results: list[dict]):
        """保存汇总结果"""
        filename = f"crawl_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"[Scheduler] 汇总结果已保存到 {filename}")

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
