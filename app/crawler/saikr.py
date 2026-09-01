"""赛氪爬虫 — 全国大学生竞赛活动平台
网站: https://www.saikr.com
技术: SPA 首页，需 Playwright 浏览器渲染获取竞赛列表

赛氪列表页（首页）包含：
- JavaScript 动态加载的竞赛卡片
- 卡片链接到 /vse/<slug> 或 https://new.saikr.com/vse/<slug>

详情页包含：
- 标题、描述、时间、主办方、奖项等信息
"""

import asyncio
import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError, extract_images_from_html
from app.crawler.extraction import (
    compact_text_fragments,
    extract_event_json_ld,
    extract_explicit_date_range,
)

logger = logging.getLogger(__name__)


class SaikrCrawler(BaseCrawler):
    platform_name = "saikr"
    base_url = "https://www.saikr.com"

    async def fetch_list(self) -> list[str]:
        """抓取赛氪首页竞赛列表

        赛氪首页是 SPA，需要 Playwright 浏览器渲染。
        """
        urls: list[str] = []
        try:
            urls = await self._fetch_list_with_playwright()
            logger.info(f"[{self.platform_name}] Playwright 获取 {len(urls)} 个链接")
        except Exception as e:
            logger.error(f"[{self.platform_name}] Playwright 列表抓取失败: {e}")
        return urls

    async def _fetch_list_with_playwright(self) -> list[str]:
        """使用 Playwright 渲染赛氪首页并提取竞赛链接"""
        from playwright.async_api import async_playwright

        urls: list[str] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(self.base_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)  # 等 JS 渲染

                # 提取所有 vse/ 链接
                html = await page.content()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "lxml")

                for a in soup.find_all("a", href=re.compile(r"(?:https?://[^/]+)?/vse/[^/?#]+")):
                    href = a.get("href", "")
                    if not href:
                        continue
                    # 标准化 URL
                    if href.startswith("http"):
                        full_url = href.split("?")[0].split("#")[0]
                    else:
                        full_url = f"https://www.saikr.com{href.split('?')[0].split('#')[0]}"
                    if full_url not in urls:
                        urls.append(full_url)

            finally:
                await browser.close()
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取赛氪详情页"""
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

        # 提取图片
        cover_image, image_urls = extract_images_from_html(soup, base_url="https://www.saikr.com")
        if cover_image:
            data["cover_image"] = cover_image
        data["image_urls"] = image_urls

        # schema.org Event 数据具有明确字段语义，优先级高于页面文案。
        for key, value in extract_event_json_ld(soup).items():
            if value and key not in data:
                data[key] = value

        # 标题
        title_el = (
            soup.select_one("h1")
            or soup.select_one("[class*='title']")
            or soup.select_one("title")
        )
        if title_el and not data.get("title"):
            title_text = title_el.get_text(strip=True)
            # 去掉常见的后缀
            for suffix in [" - 赛氪", " - 赛氪竞赛", " - 赛氪网"]:
                title_text = title_text.replace(suffix, "")
            data["title"] = title_text.strip()

        # 描述
        desc_el = (
            soup.select_one("[class*='description']")
            or soup.select_one("[class*='content']")
            or soup.select_one("meta[name='description']")
            or soup.select_one("main")
        )
        if desc_el and not data.get("description"):
            if desc_el.name == "meta":
                text = (desc_el.get("content") or "").strip()[:2000]
            else:
                text = desc_el.get_text(" ", strip=True)[:2000]
            if text and not data.get("description"):
                data["description"] = text
        # meta description 作为备选
        if not data.get("description"):
            meta_desc = soup.select_one("meta[name='description']")
            if meta_desc:
                content = meta_desc.get("content", "")
                if content:
                    data["description"] = content

        fragments = compact_text_fragments(
            soup,
            selectors=(
                ".info-item",
                ".detail-item",
                ".info-row",
                "li",
                "p",
                "tr",
                "[class*='date']",
                "[class*='time']",
            ),
        )

        # 日期只从带业务标签的局部文本或 JSON-LD 中提取，绝不扫描全页后取前两个。
        for text in fragments:
            lower = text.casefold()
            start, end = extract_explicit_date_range(text)
            if start is None:
                continue
            if any(label in lower for label in ("报名截止", "截止报名", "registration deadline")):
                data.setdefault("signup_end", end or start)
            elif any(label in lower for label in ("报名时间", "报名日期", "registration period")):
                data.setdefault("signup_start", start)
                if end:
                    data.setdefault("signup_end", end)
            elif any(
                label in lower
                for label in (
                    "比赛时间",
                    "竞赛时间",
                    "赛事时间",
                    "活动时间",
                    "举办时间",
                    "event date",
                    "event time",
                )
            ):
                data.setdefault("start_date", start)
                if end:
                    data.setdefault("end_date", end)

        # 其他事实字段同样只接受带标签的局部片段，避免跨区块吞入导航文本。
        for text in fragments:
            if not data.get("location"):
                match = re.search(r"(?:地点|举办地|城市|Location)\s*[:：]\s*(.+)$", text, re.IGNORECASE)
                if match:
                    data["location"] = match.group(1).strip()[:300]
            if not data.get("organizer"):
                match = re.search(r"(?:主办方|主办单位|组织方|Organizer)\s*[:：]\s*(.+)$", text, re.IGNORECASE)
                if match:
                    data["organizer"] = match.group(1).strip()[:100]
            if not data.get("prize"):
                match = re.search(r"(?:奖金池|奖金|奖项|奖品|Prize)\s*[:：]\s*(.+)$", text, re.IGNORECASE)
                if match:
                    data["prize"] = match.group(1).strip()[:100]
            if not data.get("mode") and re.search(r"(?:比赛形式|举办方式|活动形式|Mode)\s*[:：]", text, re.IGNORECASE):
                lower = text.casefold()
                if "线上" in lower or "online" in lower:
                    data["mode"] = "online"
                elif "线下" in lower or "in-person" in lower or "offline" in lower:
                    data["mode"] = "offline"

        # 标签
        tags: list[str] = []
        for el in soup.select("[class*='tag']"):
            text = el.get_text(strip=True)
            if text and len(text) < 50 and text not in tags:
                tags.append(text)
        if tags:
            data["tracks"] = tags

        return data


saikr_crawler = SaikrCrawler()
