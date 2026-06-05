"""
Devpost 爬虫 — 全球最大黑客松平台
对应调研报告中的第一梯队数据源

⚠️ Mock 实现 — 不执行真实网络请求
"""

from app.crawler.base import BaseCrawler, CrawlResult


class DevpostCrawler(BaseCrawler):
    platform_name = "devpost"
    base_url = "https://devpost.com/hackathons"

    async def fetch_list(self) -> list[str]:
        """Mock: 返回模拟的详情页 URL 列表"""
        return [
            "https://devpost.com/hackathons/example-hackathon-1",
            "https://devpost.com/hackathons/example-hackathon-2",
            "https://devpost.com/hackathons/example-hackathon-3",
        ]

    async def fetch_detail(self, url: str) -> CrawlResult:
        """Mock: 返回模拟的详情页原始数据"""
        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title="Mock Devpost Hackathon",
            raw_description="这是一个模拟的黑客松赛事数据，实际生产环境使用 Playwright 抓取。",
            raw_data={
                "title": "Mock Devpost Hackathon",
                "description": "Mock description from Devpost",
                "timeline": "June 2026",
                "prize": "$10,000 USD",
                "tags": ["AI", "Web", "Mobile"],
            },
        )


devpost_crawler = DevpostCrawler()