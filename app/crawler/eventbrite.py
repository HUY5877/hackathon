"""
Eventbrite 爬虫 — 公开 REST API
对应调研报告中的第一梯队数据源（有公开 API）

⚠️ Mock 实现 — 不调用真实 API
"""

from app.crawler.base import BaseCrawler, CrawlResult


class EventbriteCrawler(BaseCrawler):
    platform_name = "eventbrite"
    base_url = "https://www.eventbriteapi.com/v3/events/search"

    async def fetch_list(self) -> list[str]:
        """Mock: 返回模拟的 API 搜索结果"""
        return [
            "https://www.eventbrite.com/e/mock-hackathon-1",
            "https://www.eventbrite.com/e/mock-hackathon-2",
            "https://www.eventbrite.com/e/mock-hackathon-3",
            "https://www.eventbrite.com/e/mock-hackathon-4",
        ]

    async def fetch_detail(self, url: str) -> CrawlResult:
        """Mock: 返回模拟的 Eventbrite API 响应数据"""
        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title="Mock Eventbrite Hackathon",
            raw_description="Eventbrite 提供公开 REST API，OAuth 鉴权，数据结构化。",
            raw_data={
                "name": {"text": "Mock Eventbrite Hackathon"},
                "description": {"text": "A community hackathon event"},
                "start": {"local": "2026-07-20T09:00:00"},
                "end": {"local": "2026-07-21T18:00:00"},
                "venue": {"name": "Tech Hub", "city": "San Francisco"},
                "category": "Science & Tech",
            },
        )


eventbrite_crawler = EventbriteCrawler()