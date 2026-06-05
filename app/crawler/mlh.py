"""
MLH (Major League Hacking) 爬虫
对应调研报告中的第一梯队数据源

⚠️ Mock 实现 — 不访问内网 JSON API
"""

from app.crawler.base import BaseCrawler, CrawlResult


class MLHCrawler(BaseCrawler):
    platform_name = "mlh"
    base_url = "https://mlh.io/seasons/2026/events"

    async def fetch_list(self) -> list[str]:
        """Mock: 返回模拟的 JSON API 数据中的事件 ID"""
        return [
            "https://mlh.io/events/mock-event-1",
            "https://mlh.io/events/mock-event-2",
        ]

    async def fetch_detail(self, url: str) -> CrawlResult:
        """Mock: 返回模拟的 JSON 结构化数据"""
        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title="Mock MLH Event",
            raw_description="MLH 使用内网 JSON API，数据结构化程度最高。",
            raw_data={
                "name": "Mock MLH Hackathon",
                "date": "2026-07-15",
                "location": "Online",
                "status": "upcoming",
                "participants": 500,
            },
        )


mlh_crawler = MLHCrawler()