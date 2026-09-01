"""
Eventbrite 爬虫 — 全球活动平台
网站: https://www.eventbrite.com
技术: SSR HTML，搜索页可直接解析，无需 OAuth API key

Eventbrite 搜索 URL 格式：
    https://www.eventbrite.com/d/online/hackathon/
    https://www.eventbrite.com/d/{city}/hackathon/
详情页 URL 格式：
    https://www.eventbrite.com/e/{slug}-{id}
"""

import logging
import re
from datetime import datetime

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError
from app.crawler.extraction import compact_text_fragments, extract_event_json_ld

logger = logging.getLogger(__name__)

# 搜索路径：覆盖线上 + 主要城市（年份动态生成，避免过期）
def _build_search_paths() -> list[str]:
    """根据当前年份动态生成搜索路径"""
    current_year = datetime.now().year
    return [
        "/d/online/hackathon/",
        f"/d/online/hackathon-{current_year}/",
        "/d/united-states/hackathon/",
        "/d/china/hackathon/",
    ]

SEARCH_PATHS = _build_search_paths()


class EventbriteCrawler(BaseCrawler):
    platform_name = "eventbrite"
    base_url = "https://www.eventbrite.com"

    async def fetch_list(self) -> list[str]:
        """抓取 Eventbrite 搜索页，提取活动链接"""
        urls: list[str] = []
        for path in SEARCH_PATHS:
            try:
                resp = await self._safe_get(
                    f"{self.base_url}{path}",
                    params={"page": 1},
                )
                page_urls = self._parse_search_html(resp.text)
                new_count = 0
                for u in page_urls:
                    if u not in urls:
                        urls.append(u)
                        new_count += 1
                logger.info(f"[{self.platform_name}] {path} 获取 {len(page_urls)} 条 (新增 {new_count})")
            except CrawlerError as e:
                logger.warning(f"[{self.platform_name}] {path} 抓取失败: {e}")
                continue
        return urls

    def _parse_search_html(self, html: str) -> list[str]:
        """从搜索结果 HTML 提取活动链接

        Eventbrite 详情页 URL 格式：/e/<slug>-<digits>
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for a in soup.select('a[href*="/e/"]'):
            href = a.get("href", "")
            if not href:
                continue
            # 匹配 /e/<slug>-<id> 格式，id 为纯数字
            match = re.search(r"/e/[^/?#]+-(\d+)(?:\?|#|$)", href)
            if match:
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                # 标准化为不含 query 的 URL
                full_url = full_url.split("?")[0].split("#")[0]
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取 Eventbrite 详情页"""
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
        """从 Eventbrite 详情页提取结构化数据

        Eventbrite 页面通常包含 JSON-LD structured data，
        优先从 <script type="application/ld+json"> 提取。
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        data: dict = {"url": url}

        # 1. 优先从 JSON-LD 提取（结构化数据，最可靠）
        json_ld = self._extract_json_ld(soup)
        if json_ld:
            data.update(json_ld)

        # 2. 从 DOM 补充缺失字段
        if not data.get("title"):
            title_el = soup.select_one("h1") or soup.select_one("[class*='event-title']")
            if title_el:
                data["title"] = title_el.get_text(strip=True)

        if not data.get("description"):
            desc_el = (
                soup.select_one("[class*='description']")
                or soup.select_one(".has-user-generated-content")
                or soup.select_one("main p")
            )
            if desc_el:
                data["description"] = desc_el.get_text(strip=True)[:2000]

        # 3. 时间解析（JSON-LD 已提供 ISO 格式，这里补充文本格式）
        if not data.get("start_date"):
            date_el = soup.select_one("time") or soup.select_one("[class*='date']")
            if date_el:
                text = date_el.get_text(strip=True)
                if text:
                    data["date_info"] = text
                    # 尝试提取 datetime 属性
                    dt_attr = date_el.get("datetime") if hasattr(date_el, "get") else None
                    if dt_attr:
                        data["start_date"] = dt_attr

        # 4. 地点
        if not data.get("location"):
            location_el = (
                soup.select_one("[class*='location']")
                or soup.select_one("[class*='venue']")
                or soup.select_one("[class*='address']")
            )
            if location_el:
                data["location"] = location_el.get_text(strip=True)

        # 5. 主办方
        if not data.get("organizer"):
            organizer_el = soup.select_one("[class*='organizer']") or soup.select_one("[class*='host']")
            if organizer_el:
                data["organizer"] = organizer_el.get_text(strip=True)

        # 6. 价格
        price_el = soup.select_one("[class*='price']")
        if price_el:
            data["price"] = price_el.get_text(strip=True)

        # 7. 模式判断：优先 JSON-LD，回退时只读取局部形式/地点节点。
        if not data.get("mode"):
            fragments = compact_text_fragments(
                soup,
                selectors=("[class*='mode']", "[class*='format']", "[class*='location']", "[class*='venue']"),
                max_length=140,
            )
            evidence = " ".join(
                text
                for text in fragments
                if re.search(r"online event|virtual event|in[- ]person|hybrid", text, re.IGNORECASE)
            ).casefold()
            if "hybrid" in evidence or ("online event" in evidence and "in-person" in evidence):
                data["mode"] = "hybrid"
            elif "online event" in evidence or "virtual event" in evidence:
                data["mode"] = "online"
            elif "in-person" in evidence or "in person" in evidence:
                data["mode"] = "offline"

        # 8. 标签
        tags: list[str] = []
        for el in soup.select("[class*='tag'], [class*='badge']"):
            text = el.get_text(strip=True)
            if text and len(text) < 50 and text not in tags:
                tags.append(text)
        if tags:
            data["tracks"] = tags

        # 9. 提取图片 ──────────────────────────────
        image_urls: list[str] = list(data.get("image_urls") or [])
        base_url = self.base_url

        # 9.1 JSON-LD 中可能包含图片
        if json_ld and json_ld.get("image"):
            img = json_ld["image"]
            if isinstance(img, str):
                image_urls.append(img)
            elif isinstance(img, list) and img:
                image_urls.append(img[0])

        # 9.2 OG 封面图
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image:
            img_url = og_image.get("content")
            if img_url:
                from urllib.parse import urljoin
                full_img_url = urljoin(base_url, img_url)
                data.setdefault("cover_image", full_img_url)
                if full_img_url not in image_urls:
                    image_urls.append(full_img_url)

        # 9.3 Twitter Card 图
        if not data.get("cover_image"):
            tw_image = soup.select_one('meta[name="twitter:image"]')
            if tw_image:
                img_url = tw_image.get("content")
                if img_url:
                    from urllib.parse import urljoin
                    full_img_url = urljoin(base_url, img_url)
                    data["cover_image"] = full_img_url
                    if full_img_url not in image_urls:
                        image_urls.append(full_img_url)

        # 9.4 收集页面中所有有效图片
        for img in soup.select("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                from urllib.parse import urljoin
                full_src = urljoin(base_url, src)
                if full_src.startswith("http") and full_src not in image_urls:
                    image_urls.append(full_src)

        data["image_urls"] = image_urls

        return data

    def _extract_json_ld(self, soup) -> dict:
        """提取 schema.org Event，支持列表与 ``@graph`` 嵌套。"""
        return extract_event_json_ld(soup)


eventbrite_crawler = EventbriteCrawler()
