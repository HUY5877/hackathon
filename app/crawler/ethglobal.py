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

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError, extract_images_from_html
from app.crawler.extraction import (
    compact_text_fragments,
    extract_event_json_ld,
    extract_explicit_date_range,
)

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
        """抓取事件详情页；缺少官方标题时明确失败，不从 URL 猜名称。"""
        try:
            resp = await self._safe_get(url)
            raw_data = self._parse_detail_html(resp.text, url)
            if not raw_data.get("title"):
                return CrawlResult(
                    source_platform=self.platform_name,
                    source_url=url,
                    raw_title="",
                    raw_data=raw_data,
                    success=False,
                    error_message="missing_required_title",
                )
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=raw_data.get("title", ""),
                raw_description=(raw_data.get("description", "") or "")[:500],
                raw_data=raw_data,
            )
        except CrawlerError as e:
            logger.error(f"[{self.platform_name}] 详情爬取失败 {url}: {e}")
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title="",
                success=False,
                error_message=str(e),
            )

    def _parse_detail_html(self, html: str, url: str) -> dict:
        """从详情页 HTML 提取结构化数据"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        data: dict = {"url": url}

        cover_image, image_urls = extract_images_from_html(soup, base_url=url)
        if cover_image:
            data["cover_image"] = cover_image
        data["image_urls"] = image_urls
        for key, value in extract_event_json_ld(soup).items():
            if value and key not in data:
                data[key] = value

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("h2")
        if title_el and not data.get("title"):
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

        date_fragments = compact_text_fragments(
            soup,
            selectors=("time", "[class*='date']", "[class*='time']"),
            max_length=180,
        )
        if not data.get("start_date"):
            for text in date_fragments:
                start, end = extract_explicit_date_range(text)
                if start is None:
                    continue
                if end is None and not re.search(r"\b(date|starts?|begins?)\b", text, re.IGNORECASE):
                    continue
                data["start_date"] = start
                if end:
                    data["end_date"] = end
                break

        # 地点只接受结构化位置节点，不靠城市白名单扫描整页。
        if not data.get("location"):
            location_el = soup.select_one("[class*='location'], [class*='venue']")
            if location_el:
                location = location_el.get_text(" ", strip=True)
                if 0 < len(location) <= 150:
                    data["location"] = location

        if not data.get("mode"):
            mode_el = soup.select_one("[class*='format'], [class*='mode'], [class*='event-type']")
            mode_evidence = " ".join(
                part
                for part in (
                    mode_el.get_text(" ", strip=True) if mode_el else "",
                    str(data.get("location") or ""),
                )
                if part
            ).casefold()
            if "online" in mode_evidence or "async" in mode_evidence:
                data["mode"] = "online"
            elif "irl" in mode_evidence or "in person" in mode_evidence or "offline" in mode_evidence:
                data["mode"] = "offline"

        # 赛道标签：ETHGlobal 都是 Web3/区块链
        data["tracks"] = ["Web3", "Blockchain", "Ethereum"]

        # 主办方
        data["organizer"] = "ETHGlobal"

        return data


ethglobal_crawler = ETHGlobalCrawler()
