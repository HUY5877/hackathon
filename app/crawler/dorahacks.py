"""
DoraHacks 爬虫 — 国内最大黑客松平台
对应调研报告中的第一梯队数据源（国内）

⚠️ Mock 实现 — 不访问内网 API
"""

from app.crawler.base import BaseCrawler, CrawlResult


class DoraHacksCrawler(BaseCrawler):
    platform_name = "dorahacks"
    base_url = "https://dorahacks.io/hackathon"

    async def fetch_list(self) -> list[str]:
        """Mock: 返回模拟的详情页 URL 列表"""
        return [
            "https://dorahacks.io/hackathon/mock-hackathon-1",
            "https://dorahacks.io/hackathon/mock-hackathon-2",
        ]

    async def fetch_detail(self, url: str) -> CrawlResult:
        """Mock: 返回模拟的详情页数据"""
        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title="Mock DoraHacks Hackathon",
            raw_description="DoraHacks 是国内最大的黑客松平台，Web3+AI赛道全覆盖。",
            raw_data={
                "title": "Mock DoraHacks Hackathon",
                "prize": "$50,000 USDT",
                "tracks": ["Web3", "AI", "Infrastructure"],
                "timeline": "2026-Q3",
            },
        )


dorahacks_crawler = DoraHacksCrawler()