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

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("#challenge-title")
        if title_el:
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

        # 时间信息
        for el in soup.select("[class*='date'], [class*='time'], time"):
            text = el.get_text(strip=True)
            if not text:
                continue
            if "start" in (el.get("class") or []) or "begins" in text.lower():
                data["start_date"] = text
            elif "end" in (el.get("class") or []) or "ends" in text.lower():
                data["end_date"] = text
            elif "registration" in text.lower() or "deadline" in text.lower():
                data["signup_end"] = text

        # 地点
        location_el = soup.select_one("[class*='location']") or soup.select_one("[class*='venue']")
        if location_el:
            data["location"] = location_el.get_text(strip=True)

        # 模式（online/offline/in-person）
        body_text = soup.get_text(" ", strip=True).lower()
        if "online" in body_text and "in-person" in body_text:
            data["mode"] = "hybrid"
        elif "online" in body_text:
            data["mode"] = "online"
        elif "in-person" in body_text:
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
