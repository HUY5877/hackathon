"""Devpost 爬虫 — 全球最大黑客松平台
网站: https://devpost.com/hackathons
技术: 列表页需 Playwright 浏览器渲染，详情页 SSR 可直接 httpx 解析

Devpost 列表页 URL 格式：
    https://devpost.com/hackathons

Devpost 详情页 URL 格式（子域名）：
    https://<slug>.devpost.com/
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


class DevpostCrawler(BaseCrawler):
    platform_name = "devpost"
    base_url = "https://devpost.com/hackathons"

    async def fetch_list(self) -> list[str]:
        """抓取 Devpost 黑客松列表页

        Devpost 列表页使用 JavaScript 动态加载赛事卡片，
        必须使用 Playwright 浏览器渲染才能获取到真实链接。
        """
        urls: list[str] = []
        try:
            urls = await self._fetch_list_with_playwright()
            logger.info(f"[{self.platform_name}] Playwright 获取 {len(urls)} 个链接")
        except Exception as e:
            logger.error(f"[{self.platform_name}] Playwright 列表抓取失败: {e}")
        return urls

    async def _fetch_list_with_playwright(self) -> list[str]:
        """使用 Playwright 渲染页面并提取赛事链接"""
        from playwright.async_api import async_playwright

        urls: list[str] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(self.base_url, wait_until="networkidle", timeout=30000)
                # 等待 JavaScript 渲染，并滚动触发懒加载
                for _ in range(5):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)

                # 提取 hackathon-tile 卡片中的链接
                tiles = await page.query_selector_all(".hackathon-tile")
                for tile in tiles:
                    link = await tile.query_selector("a")
                    if link:
                        href = await link.get_attribute("href") or ""
                        if href and not href.startswith("#"):
                            # 标准化 URL（去掉 query 参数）
                            clean = href.split("?")[0].split("#")[0]
                            if clean and clean not in urls:
                                urls.append(clean)
            finally:
                await browser.close()
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取 Devpost 详情页（SSR，httpx 可直接解析）"""
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
        cover_image, image_urls = extract_images_from_html(soup, base_url=url)
        if cover_image:
            data["cover_image"] = cover_image
        data["image_urls"] = image_urls
        for key, value in extract_event_json_ld(soup).items():
            if value and key not in data:
                data[key] = value

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("#challenge-title")
        if title_el and not data.get("title"):
            data["title"] = title_el.get_text(strip=True)
        if not data.get("title"):
            # 从 title 标签提取
            title_tag = soup.select_one("title")
            if title_tag:
                text = title_tag.get_text(strip=True)
                # 去掉 " - Devpost" 后缀
                text = text.replace(" - Devpost", "").strip()
                data["title"] = text

        # 描述/摘要
        desc_el = (
            soup.select_one("[class*='description']")
            or soup.select_one("[class*='challenge-description']")
            or soup.select_one("main p")
        )
        if desc_el:
            data["description"] = desc_el.get_text(strip=True)[:2000]

        # 从 meta description 补充
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc:
            content = meta_desc.get("content", "")
            if content and not data.get("description"):
                data["description"] = content

        # 奖金
        prize_el = soup.select_one("[class*='prize']") or soup.select_one("#prize")
        if prize_el:
            data["prize"] = prize_el.get_text(strip=True)

        # 时间信息必须来自 JSON-LD 或带语义的局部节点。
        for el in soup.select("[itemprop='startDate'], [itemprop='endDate'], [class*='date'], [class*='time'], time"):
            text = el.get("datetime") or el.get("content") or el.get_text(" ", strip=True)
            start, end = extract_explicit_date_range(text)
            if start is None:
                continue
            semantic = " ".join(el.get("class") or []).casefold()
            semantic += " " + str(el.get("itemprop") or "").casefold()
            lower = str(text).casefold()
            if "registration" in semantic or "deadline" in semantic or "registration" in lower or "deadline" in lower:
                data.setdefault("signup_end", end or start)
            elif "end" in semantic or "ends" in lower:
                data.setdefault("end_date", end or start)
            elif "start" in semantic or "begins" in lower or end is not None:
                data.setdefault("start_date", start)
                if end:
                    data.setdefault("end_date", end)

        # 地点
        location_el = soup.select_one("[class*='location']") or soup.select_one("[class*='venue']")
        if location_el:
            data["location"] = location_el.get_text(strip=True)

        # 模式只接受明确的形式标签/短语，不扫描导航和页脚。
        if not data.get("mode"):
            mode_fragments = compact_text_fragments(
                soup,
                selectors=("[class*='mode']", "[class*='format']", "[class*='location']"),
                max_length=120,
            )
            mode_text = " ".join(
                text
                for text in mode_fragments
                if re.search(r"online event|in[- ]person|hybrid|event format|location", text, re.IGNORECASE)
            ).casefold()
            if "hybrid" in mode_text or ("online event" in mode_text and "in-person" in mode_text):
                data["mode"] = "hybrid"
            elif "online event" in mode_text or "virtual event" in mode_text:
                data["mode"] = "online"
            elif "in-person" in mode_text or "in person" in mode_text:
                data["mode"] = "offline"

        # 标签/赛道
        tags: list[str] = []
        for el in soup.select("[class*='tag'], [class*='track'], [class*='badge']"):
            text = el.get_text(strip=True)
            if text and len(text) < 50 and text not in tags:
                tags.append(text)
        if tags:
            data["tracks"] = tags

        # 主办方
        organizer_el = soup.select_one("[class*='organizer']") or soup.select_one("[class*='host']")
        if organizer_el:
            data["organizer"] = organizer_el.get_text(strip=True)

        # 参与人数
        participants_el = soup.select_one("[class*='participant']")
        if participants_el:
            text = participants_el.get_text(strip=True)
            nums = re.findall(r"[\d,]+", text)
            if nums:
                data["participants_count"] = int(nums[0].replace(",", ""))

        return data


devpost_crawler = DevpostCrawler()
