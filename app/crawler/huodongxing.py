"""活动行爬虫 — 城市活动发现平台
网站: https://www.huodongxing.com
技术: SSR 页面，HTML 可直接解析

活动行首页包含：
- 活动卡片，链接到 /event/<id> 或 <subdomain>.huodongxing.com/event/<id>
- 卡片包含标题、时间、地点、主办方信息

详情页包含：
- 完整标题、描述、时间、地点、主办方、票价
"""

import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError, extract_images_from_html

logger = logging.getLogger(__name__)


class HuodongxingCrawler(BaseCrawler):
    platform_name = "huodongxing"
    base_url = "https://www.huodongxing.com"

    async def fetch_list(self) -> list[str]:
        """抓取活动行首页活动列表"""
        urls: list[str] = []
        try:
            resp = await self._safe_get(self.base_url)
            page_urls = self._parse_list_html(resp.text)
            for u in page_urls:
                if u not in urls:
                    urls.append(u)
            logger.info(f"[{self.platform_name}] 获取 {len(urls)} 个活动链接")
        except CrawlerError as e:
            logger.error(f"[{self.platform_name}] 列表页失败: {e}")
        return urls

    def _parse_list_html(self, html: str) -> list[str]:
        """从首页 HTML 提取活动链接

        活动行活动链接格式：
        - /event/<id>（相对路径）
        - https://www.huodongxing.com/event/<id>（绝对路径）
        - https://<subdomain>.huodongxing.com/event/<id>（子域名）
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        for a in soup.find_all("a", href=re.compile(r"(?:https?://[^/]+)?/event/\d+")):
            href = a.get("href", "")
            if not href:
                continue
            # 标准化 URL：去掉 query 参数，补全协议
            clean = href.split("?")[0].split("#")[0]
            if clean.startswith("/"):
                clean = f"https://www.huodongxing.com{clean}"
            if clean.startswith("http") and clean not in urls:
                urls.append(clean)

        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取活动详情页"""
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
        cover_image, image_urls = extract_images_from_html(soup, base_url=url)
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
                else:
                    # 尝试提取日期格式
                    date_match = re.search(r"(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)", text)
                    if date_match and not data.get("start_date"):
                        data["start_date"] = date_match.group(1)

        # 地点
        location_el = soup.select_one("[class*='location']") or soup.select_one("[class*='venue']")
        if location_el:
            data["location"] = location_el.get_text(strip=True)

        # 主办方
        organizer_el = soup.select_one("[class*='organizer']") or soup.select_one("[class*='host']")
        if organizer_el:
            data["organizer"] = organizer_el.get_text(strip=True)

        # 票价
        price_el = soup.select_one("[class*='price']")
        if price_el:
            data["price"] = price_el.get_text(strip=True)

        # 模式判断
        body_text = soup.get_text(" ", strip=True).lower()
        if "线上" in body_text or "online" in body_text:
            data["mode"] = "online"
        elif "线下" in body_text or "in-person" in body_text:
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


huodongxing_crawler = HuodongxingCrawler()
