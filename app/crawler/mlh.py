"""
MLH (Major League Hacking) 爬虫
网站: https://mlh.io/seasons/<year>/events
技术: SSR HTML，事件卡片可直接解析

MLH 是全球最大的学生黑客松组织者之一，每年分季节举办多场活动。
"""

import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError

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
        """从 MLH 赛季页提取事件详情链接"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        # MLH 事件链接格式：/events/<slug> 或 https://mlh.io/events/<slug>
        for a in soup.select('a[href*="/events/"]'):
            href = a.get("href", "")
            if not href:
                continue
            # 仅保留详情页，排除 /seasons/.../events 列表页本身
            match = re.match(r"(?:https?://mlh\.io)?/events/([^/?#]+)$", href)
            if match:
                full_url = href if href.startswith("http") else f"https://mlh.io{href}"
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

        # 标题
        title_el = soup.select_one("h1") or soup.select_one(".event-name")
        if title_el:
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
        if date_el:
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

        # 模式
        body_text = soup.get_text(" ", strip=True).lower()
        if "online" in body_text and "in-person" in body_text:
            data["mode"] = "hybrid"
        elif "online" in body_text or "virtual" in body_text:
            data["mode"] = "online"
        elif "in-person" in body_text or "on-site" in body_text:
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

        return data

    @staticmethod
    def _parse_date_range(date_text: str, data: dict):
        """尝试从日期文本中解析起止日期

        支持格式示例：
        - "Jan 15-17, 2026"
        - "January 15 - 17, 2026"
        - "2026-01-15 to 2026-01-17"
        """
        # ISO 格式
        iso_match = re.findall(r"\d{4}-\d{2}-\d{2}", date_text)
        if len(iso_match) >= 2:
            data["start_date"] = iso_match[0]
            data["end_date"] = iso_match[1]
            return
        if len(iso_match) == 1:
            data["start_date"] = iso_match[0]
            return

        # 月份名 + 日期范围
        month_match = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s*(\d{4})", date_text)
        if month_match:
            month, day1, day2, year = month_match.groups()
            months = {
                "jan": "01", "feb": "02", "mar": "03", "apr": "04",
                "may": "05", "jun": "06", "jul": "07", "aug": "08",
                "sep": "09", "oct": "10", "nov": "11", "dec": "12",
            }
            month_num = months.get(month.lower()[:3])
            if month_num:
                data["start_date"] = f"{year}-{month_num}-{int(day1):02d}"
                data["end_date"] = f"{year}-{month_num}-{int(day2):02d}"


mlh_crawler = MLHCrawler()
