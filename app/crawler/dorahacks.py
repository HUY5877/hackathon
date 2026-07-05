"""
DoraHacks 爬虫 — 通过 CloakBrowser 绕过 WAF 爬取真实数据
网站: https://dorahacks.io/hackathon
技术: AWS WAF 人机验证，需 CloakBrowser 绕过；不可用时降级到 httpx
"""

import logging

from app.crawler.base import CrawlResult
from app.crawler.cloak_base import CloakBrowserBaseCrawler

logger = logging.getLogger(__name__)


class DoraHacksCrawler(CloakBrowserBaseCrawler):
    platform_name = "dorahacks"
    base_url = "https://dorahacks.io/hackathon"

    def _fetch_list_with_page(self, page) -> list[str]:
        """用 CloakBrowser 渲染列表页"""
        urls: list[str] = []
        for page_num in range(1, 4):
            list_url = f"{self.base_url}?page={page_num}" if page_num > 1 else self.base_url
            if not self._safe_goto(page, list_url, timeout=30000):
                logger.warning(f"[{self.platform_name}] 第 {page_num} 页导航失败")
                continue

            links = page.query_selector_all('a[href*="/hackathon/"]')
            new_count = 0
            for link in links:
                href = link.get_attribute("href") or ""
                if href and "/hackathon/" in href:
                    full_url = href if href.startswith("http") else f"https://dorahacks.io{href}"
                    if full_url != self.base_url and full_url not in urls:
                        urls.append(full_url)
                        new_count += 1
            logger.info(f"[{self.platform_name}] 第{page_num}页获取 {new_count} 个链接")
        return urls

    def _fetch_detail_with_page(self, page, url: str) -> CrawlResult:
        """用 CloakBrowser 渲染详情页"""
        if not self._safe_goto(page, url, timeout=30000):
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title="",
                success=False,
                error_message="页面导航失败",
            )

        title = self._extract_text(page, "h1")

        body_text = ""
        main_el = page.query_selector("main") or page.query_selector("article") or page.query_selector("body")
        if main_el:
            body_text = main_el.inner_text().strip()[:3000]

        raw_data = self._extract_from_page(page, url)
        raw_data["title"] = raw_data.get("title") or title
        raw_data["url"] = url
        if not raw_data.get("description"):
            raw_data["description"] = body_text[:1000]

        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title=raw_data.get("title", title),
            raw_description=body_text[:500] if body_text else None,
            raw_data=raw_data,
        )

    def _extract_from_page(self, page, url: str) -> dict:
        """从页面 DOM 中提取结构化数据"""
        data: dict = {}
        selectors = {
            "prize": [".prize", ".bounty", "[class*='prize']", "[class*='bounty']"],
            "date": [".date", ".time", "[class*='date']", "[class*='time']", "[class*='schedule']"],
            "location": [".location", ".venue", "[class*='location']", "[class*='venue']"],
            "organizer": [".organizer", "[class*='organizer']"],
        }
        for key, sel_list in selectors.items():
            for sel in sel_list:
                text = self._extract_text(page, sel)
                if text:
                    data[key] = text
                    break

        tags = self._extract_all_texts(page, "[class*='tag'], [class*='track'], [class*='badge']")
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
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            title_el = soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            body = soup.select_one("main") or soup.select_one("body")
            body_text = body.get_text(strip=True)[:2000] if body else ""
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=title,
                raw_description=body_text[:500],
                raw_data={"title": title, "description": body_text, "url": url, "_fallback": "httpx"},
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
