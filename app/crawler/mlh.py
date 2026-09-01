"""
MLH (Major League Hacking) 爬虫
网站: https://mlh.io/seasons/<year>/events
技术: SSR HTML，事件卡片可直接解析

MLH 是全球最大的学生黑客松组织者之一，每年分季节举办多场活动。
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


class MLHCrawler(BaseCrawler):
    platform_name = "mlh"
    base_url = "https://mlh.io"

    # MLH 按年度组织活动，URL 模板
    SEASON_URL_TEMPLATE = "https://mlh.io/seasons/{year}/events"

    async def fetch_list(self) -> list[str]:
        """抓取 MLH 赛季事件列表"""
        urls: list[str] = []
        # 尝试当前年与下一年
        from datetime import datetime
        current_year = datetime.now().year
        for year in [current_year, current_year + 1]:
            season_url = self.SEASON_URL_TEMPLATE.format(year=year)
            try:
                resp = await self._safe_get(season_url)
                page_urls = self._parse_list_html(resp.text)
                if page_urls:
                    for u in page_urls:
                        if u not in urls:
                            urls.append(u)
                    logger.info(f"[{self.platform_name}] {year} 赛季获取 {len(page_urls)} 个链接")
            except CrawlerError as e:
                logger.warning(f"[{self.platform_name}] {year} 赛季抓取失败: {e}")
                continue
        return urls

    def _parse_list_html(self, html: str) -> list[str]:
        """从 MLH 赛季页提取事件详情链接

        MLH 页面将事件数据嵌入在 <script type="application/json"> 中，
        每个事件包含 slug、name、url（如 /events/<slug>/prizes）等字段。
        """
        from bs4 import BeautifulSoup
        import json
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        # 1. 从页面内嵌 JSON 中提取事件数据（主要来源）
        for script in soup.find_all("script", type="application/json"):
            text = script.string or ""
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue

            def _extract_events(node):
                """递归查找包含 slug 和 url 的事件对象"""
                if isinstance(node, dict):
                    if (
                        "slug" in node
                        and "url" in node
                        and isinstance(node.get("url"), str)
                        and "/events/" in node["url"]
                    ):
                        event_url = node["url"]
                        event_match = re.search(r"/events/([^/?#]+)", event_url)
                        if not event_match:
                            return
                        # Embedded records may point to /prizes, /schedule, etc.
                        # Persist only the canonical event page.
                        full_url = f"https://mlh.io/events/{event_match.group(1)}"
                        if full_url not in urls:
                            urls.append(full_url)
                    for v in node.values():
                        _extract_events(v)
                elif isinstance(node, list):
                    for item in node:
                        _extract_events(item)

            _extract_events(data)

        # 2. 回退：从 HTML 锚点链接中匹配 /events/<slug> 格式
        if not urls:
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                match = re.match(r"(?:https?://(?:www\.)?mlh\.io)?/events/([^/?#]+)", href)
                if match:
                    full_url = f"https://mlh.io/events/{match.group(1)}"
                    if full_url not in urls:
                        urls.append(full_url)

        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取 MLH 事件详情页"""
        try:
            resp = await self._safe_get(url)
            raw_data = self._parse_detail_html(resp.text, url)
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=raw_data.get("title", ""),
                raw_description=(raw_data.get("description", "") or "")[:500],
                raw_data=raw_data,
                image_urls=raw_data.get("image_urls", []),
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
        """从 MLH 事件详情页提取结构化数据"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        data: dict = {"url": url}
        for key, value in extract_event_json_ld(soup).items():
            if value:
                data[key] = value

        # 标题
        title_el = soup.select_one("h1") or soup.select_one(".event-name")
        if title_el and not data.get("title"):
            data["title"] = title_el.get_text(strip=True)

        # 描述
        desc_el = (
            soup.select_one(".event-description")
            or soup.select_one("[class*='description']")
            or soup.select_one("main p")
        )
        if desc_el:
            data["description"] = desc_el.get_text(strip=True)[:2000]

        # 时间（MLH 通常用 .event-date 或 time 元素）
        date_el = soup.select_one("time") or soup.select_one("[class*='date']")
        if date_el and not data.get("start_date"):
            date_text = date_el.get_text(strip=True)
            data["date_info"] = date_text
            # 尝试解析起止日期（格式如 "Jan 15-17, 2026"）
            self._parse_date_range(date_text, data)

        # 地点
        location_el = (
            soup.select_one("[class*='location']")
            or soup.select_one("[class*='venue']")
            or soup.select_one("[class*='address']")
        )
        if location_el:
            data["location"] = location_el.get_text(strip=True)

        # 模式只读取形式/地点等局部节点。
        if not data.get("mode"):
            fragments = compact_text_fragments(
                soup,
                selectors=("[class*='mode']", "[class*='format']", "[class*='location']", "[class*='venue']"),
                max_length=120,
            )
            evidence = " ".join(
                text
                for text in fragments
                if re.search(r"online|virtual|in[- ]person|on-site|hybrid", text, re.IGNORECASE)
            ).casefold()
            if "hybrid" in evidence or ("online" in evidence and "in-person" in evidence):
                data["mode"] = "hybrid"
            elif "online" in evidence or "virtual" in evidence:
                data["mode"] = "online"
            elif "in-person" in evidence or "in person" in evidence or "on-site" in evidence:
                data["mode"] = "offline"

        # 主办方（MLH 通常是 MLH 或合作高校）
        organizer_el = soup.select_one("[class*='organizer']") or soup.select_one("[class*='host']")
        if organizer_el:
            data["organizer"] = organizer_el.get_text(strip=True)
        else:
            data["organizer"] = "Major League Hacking"

        # 标签
        tags: list[str] = []
        for el in soup.select("[class*='tag'], [class*='badge']"):
            text = el.get_text(strip=True)
            if text and len(text) < 50 and text not in tags:
                tags.append(text)
        if tags:
            data["tracks"] = tags

        # 报名链接
        signup_el = soup.select_one('a[href*="register"]') or soup.select_one('a[href*="signup"]')
        if signup_el:
            data["signup_url"] = signup_el.get("href", "")

        # 提取图片
        cover_image, image_urls = extract_images_from_html(soup, base_url=self.base_url)
        data["cover_image"] = cover_image
        data["image_urls"] = image_urls

        return data

    @staticmethod
    def _parse_date_range(date_text: str, data: dict):
        """尝试从日期文本中解析起止日期

        支持格式示例：
        - "Jan 15-17, 2026"
        - "January 15 - 17, 2026"
        - "2026-01-15 to 2026-01-17"
        """
        start, end = extract_explicit_date_range(date_text)
        if start:
            data["start_date"] = start
        if end:
            data["end_date"] = end


mlh_crawler = MLHCrawler()
