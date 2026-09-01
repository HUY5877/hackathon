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
from app.crawler.extraction import (
    compact_text_fragments,
    extract_event_json_ld,
    extract_explicit_date_range,
)

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

        for key, value in extract_event_json_ld(soup).items():
            if value and key not in data:
                data[key] = value

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("[class*='title']")
        if title_el and not data.get("title"):
            data["title"] = title_el.get_text(strip=True)

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

        # 活动行详情页常用“标签：值”展示时间、地点和主办方。
        for el in soup.select(".info-item, .detail-item, .info-row"):
            text = el.get_text(" ", strip=True)
            time_match = re.search(r"(?:活动时间|举办时间|时间)\s*[:：]\s*(.+)", text)
            if time_match:
                start, end = extract_explicit_date_range(time_match.group(1))
                if start:
                    data.setdefault("start_date", start)
                if end:
                    data.setdefault("end_date", end)
            location_match = re.search(r"地点\s*[:：]\s*(.+)", text)
            if location_match:
                data.setdefault("location", location_match.group(1).strip())
            organizer_match = re.search(r"主办方\s*[:：]\s*(.+)", text)
            if organizer_match:
                data.setdefault("organizer", organizer_match.group(1).strip())

        # 非结构化时间节点必须带明确标签；generic "date" 可能只是发布日期。
        for el in soup.select("[itemprop='startDate'], [itemprop='endDate'], [class*='event-date'], [class*='event-time'], [class*='activity-time'], time"):
            text = el.get("datetime") or el.get("content") or el.get_text(" ", strip=True)
            start, end = extract_explicit_date_range(text)
            if start is None:
                continue
            semantic = " ".join(el.get("class") or []).casefold()
            semantic += " " + str(el.get("itemprop") or "").casefold()
            lower = str(text).casefold()
            has_event_semantics = any(
                token in semantic
                for token in ("event", "activity", "startdate", "enddate")
            ) or any(
                token in lower
                for token in ("活动时间", "举办时间", "开始", "结束", "报名截止")
            )
            if not has_event_semantics:
                continue
            if "end" in semantic or "end" in lower or "结束" in lower:
                data.setdefault("end_date", end or start)
            elif "deadline" in semantic or "deadline" in lower or "报名截止" in lower:
                data.setdefault("signup_end", end or start)
            else:
                data.setdefault("start_date", start)
                if end:
                    data.setdefault("end_date", end)

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

        # 模式只使用地点或带“活动形式/举办方式”标签的局部文本。
        mode_evidence = [str(data.get("location") or "")]
        mode_evidence.extend(
            text
            for text in compact_text_fragments(soup, max_length=120)
            if re.search(r"(?:活动形式|举办方式|参与方式)\s*[:：]", text)
        )
        mode_text = " ".join(mode_evidence).casefold()
        if "线上" in mode_text or "online" in mode_text:
            data["mode"] = "online"
        elif "线下" in mode_text or "in-person" in mode_text or "offline" in mode_text:
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
