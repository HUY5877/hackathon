"""
ETHGlobal 爬虫 — 以太坊/Web3 全球黑客松平台
网站: https://ethglobal.com/events
技术: SSR 列表页，HTML 可直接解析

ETHGlobal 列表页包含每个事件的：
- 名称、日期、地点、类型（IRL Hackathon / Online / Conference）
- 链接到详情页 /events/<slug>

特点：
- 列表页已包含丰富结构化信息，优先从列表页提取
- 详情页可能有反爬（500），需降级处理
- 覆盖 Web3/区块链赛道
"""

import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError

logger = logging.getLogger(__name__)


class ETHGlobalCrawler(BaseCrawler):
    platform_name = "ethglobal"
    base_url = "https://ethglobal.com/events"

    async def fetch_list(self) -> list[str]:
        """抓取 ETHGlobal 事件列表页"""
        urls: list[str] = []
        try:
            resp = await self._safe_get(self.base_url)
            page_urls = self._parse_list_html(resp.text)
            for u in page_urls:
                if u not in urls:
                    urls.append(u)
            logger.info(f"[{self.platform_name}] 获取 {len(urls)} 个事件链接")
        except CrawlerError as e:
            logger.error(f"[{self.platform_name}] 列表页失败: {e}")
        return urls

    def _parse_list_html(self, html: str) -> list[str]:
        """从列表页 HTML 提取事件链接"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        # ETHGlobal 事件链接：/events/<slug>
        for a in soup.select('a[href*="/events/"]'):
            href = a.get("href", "")
            if not href:
                continue
            # 仅保留详情页（/events/<slug>），排除列表页本身
            match = re.match(r"(?:https?://ethglobal\.com)?/events/([^/?#]+)$", href)
            if match:
                slug = match.group(1)
                # 排除 "events" 本身
                if slug == "events":
                    continue
                full_url = href if href.startswith("http") else f"https://ethglobal.com{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取事件详情页（含降级：从列表页链接文本提取）"""
        try:
            resp = await self._safe_get(url)
            # 如果详情页返回错误（如 500），尝试从 URL slug 提取基本信息
            raw_data = self._parse_detail_html(resp.text, url)
            if not raw_data.get("title"):
                # 降级：从 URL slug 推断名称
                slug = url.rstrip("/").split("/")[-1]
                raw_data["title"] = slug.replace("-", " ").replace("_", " ").title()
                raw_data["_fallback"] = "url_slug"
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=raw_data.get("title", ""),
                raw_description=(raw_data.get("description", "") or "")[:500],
                raw_data=raw_data,
            )
        except CrawlerError as e:
            logger.warning(f"[{self.platform_name}] 详情爬取失败 {url}: {e}")
            # 降级：返回带 URL 的最小结果
            slug = url.rstrip("/").split("/")[-1]
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=slug.replace("-", " ").title(),
                raw_description="",
                raw_data={"title": slug.replace("-", " ").title(), "url": url, "_fallback": "error"},
            )

    def _parse_detail_html(self, html: str, url: str) -> dict:
        """从详情页 HTML 提取结构化数据"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        data: dict = {"url": url}

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("h2")
        if title_el:
            title_text = title_el.get_text(strip=True)
            # ETHGlobal 标题通常包含 "ETHGlobal <Name> <Year>"
            if title_text:
                data["title"] = title_text

        # meta description
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc:
            content = meta_desc.get("content", "")
            if content:
                data["description"] = content

        # 正文
        body_el = soup.select_one("main") or soup.select_one("body")
        if body_el:
            body_text = body_el.get_text(" ", strip=True)[:3000]
            if not data.get("description"):
                data["description"] = body_text

        # 日期：查找包含月份关键词的文本
        months = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        for el in soup.select("[class*='date'], [class*='time'], time, p, span, div"):
            text = el.get_text(" ", strip=True)
            if re.search(months, text) and re.search(r"\d{4}", text):
                if "start" not in data:
                    data["start_date"] = text[:100]
                break

        # 地点：查找城市/国家关键词
        location_patterns = [
            r"(Lisbon|Tokyo|Mumbai|San Francisco|New York|London|Berlin|Paris|Singapore|Seoul|Online|Async)",
        ]
        for el in soup.select("[class*='location'], [class*='venue'], p, span, div"):
            text = el.get_text(" ", strip=True)
            for pattern in location_patterns:
                match = re.search(pattern, text)
                if match and len(text) < 200:
                    data["location"] = text[:100]
                    break
            if data.get("location"):
                break

        # 模式判断
        body_lower = (data.get("description", "") + " " + data.get("location", "")).lower()
        if "online" in body_lower or "async" in body_lower:
            data["mode"] = "online"
        elif "irl" in body_lower or "in person" in body_lower:
            data["mode"] = "offline"

        # 赛道标签：ETHGlobal 都是 Web3/区块链
        data["tracks"] = ["Web3", "Blockchain", "Ethereum"]

        # 主办方
        data["organizer"] = "ETHGlobal"

        return data


ethglobal_crawler = ETHGlobalCrawler()
