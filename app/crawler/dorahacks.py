"""DoraHacks 爬虫 — 通过 CloakBrowser 绕过 WAF 爬取真实数据
网站: https://dorahacks.io/hackathon
技术: AWS WAF 人机验证，需 CloakBrowser stealth 绕过
"""

import logging
import re

from app.crawler.base import CrawlResult, extract_images_from_html
from app.crawler.cloak_base import CloakBrowserBaseCrawler

logger = logging.getLogger(__name__)


class DoraHacksCrawler(CloakBrowserBaseCrawler):
    platform_name = "dorahacks"
    base_url = "https://dorahacks.io/hackathon"

    def _parse_list_html(self, html: str) -> list[str]:
        """从列表页 HTML 提取 hackathon 链接"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        # DoraHacks 列表页中 hackathon 卡片链接
        for a in soup.select('a[href*="/hackathon/"]'):
            href = a.get("href", "")
            if not href:
                continue
            # 匹配 /hackathon/<id> 格式
            match = re.match(r"(?:https?://dorahacks\.io)?/hackathon/([\w\-]+)/?$", href)
            if match:
                slug = match.group(1)
                full_url = f"https://dorahacks.io/hackathon/{slug}"
                if full_url not in urls:
                    urls.append(full_url)

        return urls

    def _parse_detail_html(self, html: str, url: str) -> dict:
        """从详情页 HTML 提取结构化数据"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        data: dict = {"url": url}

        # 提取图片
        cover_image, image_urls = extract_images_from_html(soup, base_url="https://dorahacks.io")
        if cover_image:
            data["cover_image"] = cover_image
        data["image_urls"] = image_urls

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("[class*='title']")
        if title_el:
            data["title"] = title_el.get_text(strip=True)

        # 描述
        desc_el = (
            soup.select_one("[class*='description']")
            or soup.select_one("main")
            or soup.select_one("article")
        )
        if desc_el:
            data["description"] = desc_el.get_text(" ", strip=True)[:2000]

        # 奖金
        prize_el = soup.select_one("[class*='prize']") or soup.select_one("[class*='bounty']")
        if prize_el:
            data["prize"] = prize_el.get_text(strip=True)

        # 时间
        for el in soup.select("[class*='date'], [class*='time'], time"):
            text = el.get_text(strip=True)
            if text:
                if "start" in text.lower() or "begin" in text.lower():
                    data["start_date"] = text
                elif "end" in text.lower():
                    data["end_date"] = text
                elif "deadline" in text.lower():
                    data["signup_end"] = text

        # 地点
        location_el = soup.select_one("[class*='location']") or soup.select_one("[class*='venue']")
        if location_el:
            data["location"] = location_el.get_text(strip=True)

        # 主办方
        organizer_el = soup.select_one("[class*='organizer']") or soup.select_one("[class*='host']")
        if organizer_el:
            data["organizer"] = organizer_el.get_text(strip=True)

        # 标签
        tags: list[str] = []
        for el in soup.select("[class*='tag'], [class*='track']"):
            text = el.get_text(strip=True)
            if text and len(text) < 50 and text not in tags:
                tags.append(text)
        if tags:
            data["tracks"] = tags

        return data

    # ── httpx 降级方案 ──────────────────────────────

    async def _fetch_list_via_httpx_async(self) -> list[str]:
        """httpx 降级：DoraHacks 是 SPA，httpx 无法获取完整列表"""
        logger.warning(f"[{self.platform_name}] httpx 降级无法获取 SPA 列表，返回空")
        return []

    async def _fetch_detail_via_httpx_async(self, url: str) -> CrawlResult:
        """httpx 降级：尝试获取基础 HTML"""
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
        except Exception as e:
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title="",
                success=False,
                error_message=f"httpx 降级失败: {e}",
            )


dorahacks_crawler = DoraHacksCrawler()
