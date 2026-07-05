"""
Hackathon.com 爬虫 — 全球黑客松聚合平台
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

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError

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

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("h2")
        if title_el:
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

        # 结构化字段提取：Hackathon.com 详情页包含
        # "Organized by X", "In-person only", "Student", 日期等
        full_text = soup.get_text(" ", strip=True)

        # 组织者：匹配 "Organized by X." 到句号
        org_match = re.search(r"Organized by\s+([A-Za-z0-9\s,&.]+?)\.", full_text)
        if org_match:
            data["organizer"] = org_match.group(1).strip()[:100]

        # 形式（In-person / Online）
        if re.search(r"in[- ]person", full_text, re.IGNORECASE):
            data["mode"] = "offline"
        elif re.search(r"\bonline\b", full_text, re.IGNORECASE):
            data["mode"] = "online"

        # 受众
        if re.search(r"\bstudent\b", full_text, re.IGNORECASE):
            data["audience"] = "student"

        # 日期：查找 "Month DD, YYYY" 或 "DD Month YYYY" 格式
        date_patterns = [
            r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4})",
            r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
        ]
        dates_found: list[str] = []
        for pattern in date_patterns:
            for match in re.finditer(pattern, full_text):
                d = match.group(1)
                if d not in dates_found:
                    dates_found.append(d)
        if dates_found:
            data["start_date"] = dates_found[0]
            if len(dates_found) > 1:
                data["end_date"] = dates_found[1]

        # 地点
        loc_match = re.search(r"(?:Location|Venue|Place)[:\s]+([A-Za-z\s,]+?)(?=\s{2}|$)", full_text)
        if loc_match:
            data["location"] = loc_match.group(1).strip()[:100]

        # 奖金
        prize_match = re.search(r"(?:Prize|Award|Cash)[:\s]*\$?([\d,]+)", full_text, re.IGNORECASE)
        if prize_match:
            data["prize"] = f"${prize_match.group(1)}"

        return data


hackathon_com_crawler = HackathonComCrawler()
