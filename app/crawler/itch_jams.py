"""itch.io Jams 爬虫 — 全球最大游戏开发 Jam 平台
网站: https://itch.io/jams
技术: SSR 列页 + 详情页，HTML 可直接解析

itch.io/jams 列表页包含：
- 大量 Jam 卡片（500+），链接到 /jam/<slug>
- 卡片含名称、日期范围、参与人数

详情页包含：
- 完整描述、日期范围、提交数、参与数
- 结构化的 .date_range 元素

特点：
- 数据量最大（483+ 链接）
- 游戏开发赛道（Game Jam）
- 日期格式规范（ISO 8601）
"""

import logging
import re
from datetime import datetime

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError, extract_images_from_html

logger = logging.getLogger(__name__)


class ItchJamsCrawler(BaseCrawler):
    platform_name = "itch_jams"
    base_url = "https://itch.io"
    jams_url = "https://itch.io/jams"

    async def fetch_list(self) -> list[str]:
        """抓取 itch.io Jams 列表页（支持分页）"""
        urls: list[str] = []
        # itch.io 通过 page 参数分页
        for page in range(1, 4):
            try:
                params = {"page": page} if page > 1 else None
                resp = await self._safe_get(self.jams_url, params=params)
                page_urls = self._parse_list_html(resp.text)
                if not page_urls:
                    logger.info(f"[{self.platform_name}] 第 {page} 页无更多结果，停止")
                    break
                new_count = 0
                for u in page_urls:
                    if u not in urls:
                        urls.append(u)
                        new_count += 1
                logger.info(f"[{self.platform_name}] 第 {page} 页获取 {new_count} 个新链接")
                # 如果没有新链接，说明已到末页
                if new_count == 0:
                    break
            except CrawlerError as e:
                logger.error(f"[{self.platform_name}] 第 {page} 页失败: {e}")
                break
        return urls

    def _parse_list_html(self, html: str) -> list[str]:
        """从列表页 HTML 提取 Jam 链接"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        # Jam 链接：/jam/<slug>
        for a in soup.select('a[href*="/jam/"]'):
            href = a.get("href", "")
            if not href:
                continue
            # 仅保留详情页（/jam/<slug>），排除子路径
            match = re.match(r"(?:https?://itch\.io)?/jam/([^/?#]+)$", href)
            if match:
                slug = match.group(1)
                full_url = href if href.startswith("http") else f"https://itch.io{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取 Jam 详情页"""
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

        # 标题：itch.io jam 详情页标题在 .jam_title 或 h1
        title_el = (
            soup.select_one(".jam_title")
            or soup.select_one("h1")
            or soup.select_one("h2")
        )
        if title_el:
            title_text = title_el.get_text(strip=True)
            if title_text and title_text.lower() != "itch.io":
                data["title"] = title_text

        # 如果标题没找到，从 URL slug 推断
        if not data.get("title"):
            slug = url.rstrip("/").split("/")[-1]
            data["title"] = slug.replace("-", " ").replace("_", " ").title()

        # 日期范围：itch.io 使用 .date_range 元素，格式为
        # "Submissions open from 2026-07-22 17:00:00 to 2026-07-26 17:00:00"
        date_range_el = soup.select_one(".date_range")
        if date_range_el:
            date_text = date_range_el.get_text(" ", strip=True)
            data["date_range_raw"] = date_text
            # 提取 ISO 日期
            iso_dates = re.findall(r"\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?", date_text)
            if len(iso_dates) >= 2:
                data["start_date"] = iso_dates[0]
                data["end_date"] = iso_dates[1]
            elif len(iso_dates) == 1:
                data["start_date"] = iso_dates[0]

        # 描述：jam_content 或 .jam_content
        desc_el = (
            soup.select_one(".jam_content")
            or soup.select_one("#jam_content")
            or soup.select_one(".content")
            or soup.select_one("main")
        )
        if desc_el:
            desc_text = desc_el.get_text(" ", strip=True)[:2000]
            if desc_text:
                data["description"] = desc_text

        # 参与统计：itch.io 显示 "X joined" 或 "X submissions"
        full_text = soup.get_text(" ", strip=True)
        joined_match = re.search(r"([\d,]+)\s+(?:joined|entries|submissions)", full_text, re.IGNORECASE)
        if joined_match:
            count = int(joined_match.group(1).replace(",", ""))
            data["participants_count"] = count

        # 模式：Game Jam 通常是线上
        data["mode"] = "online"

        # 赛道标签：游戏开发
        data["tracks"] = ["Game Development", "Game Jam"]

        # 主办方：查找 "Hosted by" 或 "by <name>"
        host_match = re.search(r"(?:Hosted by|by)\s+([A-Za-z0-9_\s\-]+?)(?=\s{2}|$)", full_text)
        if host_match:
            data["organizer"] = host_match.group(1).strip()[:100]

        # 报名状态：根据日期判断
        if data.get("start_date"):
            try:
                start = datetime.fromisoformat(data["start_date"].split()[0])
                now = datetime.now()
                if now < start:
                    data["status"] = "upcoming"
                elif data.get("end_date"):
                    end = datetime.fromisoformat(data["end_date"].split()[0])
                    if now > end:
                        data["status"] = "ended"
                    else:
                        data["status"] = "ongoing"
            except (ValueError, TypeError):
                pass

        return data


itch_jams_crawler = ItchJamsCrawler()
