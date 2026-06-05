"""
爬虫基类 — 定义所有平台爬虫的统一接口
对应架构图：自动化爬虫引擎 (D1)
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """单条爬取结果（原始数据，未经 LLM 清洗）"""
    source_platform: str
    source_url: str
    raw_title: str
    raw_description: str | None = None
    raw_data: dict = field(default_factory=dict)
    crawled_at: datetime = field(default_factory=datetime.now)


class BaseCrawler(ABC):
    """爬虫基类"""

    # 子类必须定义
    platform_name: str = "unknown"
    base_url: str = ""

    def __init__(self, request_delay: float = 2.0):
        self.request_delay = request_delay
        self._session = None

    @abstractmethod
    async def fetch_list(self) -> list[str]:
        """抓取列表页，返回详情页 URL 列表"""
        ...

    @abstractmethod
    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取详情页，返回原始数据"""
        ...

    async def _delay(self):
        """请求间延迟"""
        await asyncio.sleep(self.request_delay)

    async def run(self) -> list[CrawlResult]:
        """执行完整爬取流程"""
        logger.info(f"[{self.platform_name}] 开始爬取...")
        detail_urls = await self.fetch_list()
        logger.info(f"[{self.platform_name}] 获取到 {len(detail_urls)} 个详情页链接")

        results = []
        for url in detail_urls:
            try:
                result = await self.fetch_detail(url)
                results.append(result)
                await asyncio.sleep(self.request_delay)
            except Exception as e:
                logger.error(f"[{self.platform_name}] 抓取失败: {url}, 错误: {e}")

        logger.info(f"[{self.platform_name}] 爬取完成，共 {len(results)} 条结果")
        return results