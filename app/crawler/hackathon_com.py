"""Hackathon.com 爬虫 — 全球黑客松聚合平台
网站: https://www.hackathon.com/
技术: SSR 列表页 + 详情页，HTML 可直接解析

Hackathon.com 列表页包含：
- 事件卡片，链接到 /event/<slug-id>
- 卡片中包含标题、组织者、形式（线上/线下）、受众（学生/公众）

详情页包含：
- 完整标题、描述、日期、地点、报名信息
"""

import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError, extract_images_from_html
from app.crawler.extraction import (
    compact_text_fragments,
    extract_event_json_ld,
    extract_explicit_date_range,
    is_standalone_date_expression,
)

logger = logging.getLogger(__name__)


class HackathonComCrawler(BaseCrawler):
    platform_name = "hackathon_com"
    base_url = "https://www.hackathon.com"

    async def fetch_list(self) -> list[str]:
        """抓取 Hackathon.com 首页事件列表"""
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
        """从首页 HTML 提取事件链接"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        # 事件链接：/event/<slug-id>
        for a in soup.select('a[href*="/event/"]'):
            href = a.get("href", "")
            if not href:
                continue
            # 仅保留详情页（/event/<slug>），排除其他子路径
            match = re.search(r"/event/([a-z0-9\-]+)$", href)
            if match:
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取事件详情页"""
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
        """从详情页 HTML 提取结构化数据"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        data: dict = {"url": url}

        # 提取图片（通用函数）
        cover_image, image_urls = extract_images_from_html(soup, base_url=self.base_url)
        if cover_image:
            data["cover_image"] = cover_image
        data["image_urls"] = image_urls

        for key, value in extract_event_json_ld(soup).items():
            if value and key not in data:
                data[key] = value

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("h2")
        if title_el and not data.get("title"):
            data["title"] = title_el.get_text(strip=True)

        # meta description
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc:
            content = meta_desc.get("content", "")
            if content:
                data["description"] = content

        # 正文内容
        body_el = (
            soup.select_one("[class*='event-detail']")
            or soup.select_one("[class*='content']")
            or soup.select_one("main")
            or soup.select_one("body")
        )
        if body_el:
            body_text = body_el.get_text(" ", strip=True)[:3000]
            if not data.get("description"):
                data["description"] = body_text

        fragments = compact_text_fragments(
            soup,
            selectors=(
                "time",
                "[itemprop='startDate']",
                "[itemprop='endDate']",
                "[class*='date']",
                "[class*='time']",
                "p",
                "li",
            ),
            max_length=240,
        )

        # 属性带有 schema.org 语义时直接按字段读取。
        for field, selector in (
            ("start_date", "[itemprop='startDate']"),
            ("end_date", "[itemprop='endDate']"),
        ):
            if data.get(field):
                continue
            element = soup.select_one(selector)
            if element:
                value = element.get("content") or element.get("datetime") or element.get_text(" ", strip=True)
                start, _ = extract_explicit_date_range(value)
                if start:
                    data[field] = start

        # 未结构化的 HTML 只接受局部明确范围或带 Starts/Ends 标签的值。
        for text in fragments:
            start, end = extract_explicit_date_range(text)
            if start is None:
                continue
            lower = text.casefold()
            if re.search(r"\b(published|publication|updated|last modified)\b", lower):
                continue
            if re.search(r"\b(registration|application|deadline)\b", lower):
                if "deadline" in lower:
                    data.setdefault("signup_end", end or start)
                elif end is not None:
                    data.setdefault("signup_start", start)
                    data.setdefault("signup_end", end)
                continue
            has_event_label = bool(
                re.search(
                    r"\b(event|hackathon)\s+(?:date|dates|time)|\b(?:starts?|begins?|ends?)\b",
                    lower,
                )
            )
            if end is not None and (
                has_event_label or is_standalone_date_expression(text, start, end)
            ):
                data.setdefault("start_date", start)
                data.setdefault("end_date", end)
                break
            if has_event_label and not re.search(r"\bends?\b", lower):
                data.setdefault("start_date", start)
            elif re.search(r"\bends?\b", lower):
                data.setdefault("end_date", start)

        for text in fragments:
            if not data.get("organizer"):
                match = re.search(r"Organized by\s+(.+?)(?:\.|$)", text, re.IGNORECASE)
                if match:
                    data["organizer"] = match.group(1).strip()[:100]
            if not data.get("location"):
                match = re.search(r"(?:Location|Venue|Place)\s*[:：]\s*(.+)$", text, re.IGNORECASE)
                if match:
                    data["location"] = match.group(1).strip()[:100]
            if not data.get("prize"):
                match = re.search(r"(?:Prize|Award|Cash)\s*[:：]\s*(\$?[\d,]+)", text, re.IGNORECASE)
                if match:
                    value = match.group(1)
                    data["prize"] = value if value.startswith("$") else f"${value}"
            if not data.get("mode"):
                if re.search(r"\b(in[- ]person only|offline event)\b", text, re.IGNORECASE):
                    data["mode"] = "offline"
                elif re.search(r"\b(online only|online event|virtual event)\b", text, re.IGNORECASE):
                    data["mode"] = "online"
            if "audience" not in data and re.search(r"\bstudent\b", text, re.IGNORECASE):
                data["audience"] = "student"

        return data


hackathon_com_crawler = HackathonComCrawler()
