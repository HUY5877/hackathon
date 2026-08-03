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

        # 标题
        title_el = (
            soup.select_one("h1")
            or soup.select_one("[class*='title']")
            or soup.select_one("title")
        )
        if title_el:
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
        if desc_el:
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

        # 时间信息
        full_text = soup.get_text(" ", strip=True)
        for pattern in [
            r"(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)",
            r"(\d{4}-\d{2}-\d{2})",
        ]:
            matches = re.findall(pattern, full_text)
            if matches:
                dates = list(dict.fromkeys(matches))[:2]
                if len(dates) >= 1:
                    data["start_date"] = dates[0]
                if len(dates) >= 2:
                    data["end_date"] = dates[1]
                break

        # 地点
        loc_match = re.search(
            r"(?:地点|举办地|城市|Location)[:\s]*([\u4e00-\u9fa5]+(?:省|市|区|县)?)",
            full_text,
        )
        if loc_match:
            data["location"] = loc_match.group(1)

        # 主办方
        org_match = re.search(
            r"(?:主办方|主办单位|组织方|Organizer)[:\s]*([\u4e00-\u9fa5a-zA-Z\s,]+?)(?:\n|$)",
            full_text,
            re.IGNORECASE,
        )
        if org_match:
            data["organizer"] = org_match.group(1).strip()[:100]

        # 奖金/奖项
        prize_match = re.search(
            r"(?:奖金|奖项|奖品|奖金池| Prize)[:\s]*([^\n]+)", full_text, re.IGNORECASE
        )
        if prize_match:
            data["prize"] = prize_match.group(1).strip()[:100]

        # 模式：线上/线下
        if "线上" in full_text or "online" in full_text.lower():
            data["mode"] = "online"
        elif "线下" in full_text or "in-person" in full_text.lower():
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
