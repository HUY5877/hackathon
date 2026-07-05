"""
赛氪 (SaiKr) 爬虫 — 国内大学生竞赛信息平台
网站: https://www.saikr.com/vs
技术: SSR 页面，可用 CloakBrowser 渲染；不可用时降级到 httpx
"""

import logging

from app.crawler.base import CrawlResult
from app.crawler.cloak_base import CloakBrowserBaseCrawler

logger = logging.getLogger(__name__)


class SaiKrCrawler(CloakBrowserBaseCrawler):
    platform_name = "saikr"
    base_url = "https://www.saikr.com/vs"

    def _fetch_list_with_page(self, page) -> list[str]:
        """用 CloakBrowser 渲染列表页"""
        urls: list[str] = []
        if not self._safe_goto(page, self.base_url, timeout=30000):
            return urls

        links = page.query_selector_all('a[href*="/v/"]')
        for link in links:
            href = link.get_attribute("href") or ""
            if href and "/v/" in href:
                full_url = href if href.startswith("http") else f"https://www.saikr.com{href}"
                if full_url not in urls:
                    urls.append(full_url)
        logger.info(f"[{self.platform_name}] 列表页获取 {len(urls)} 个链接")
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
        main_el = (
            page.query_selector(".detail-content")
            or page.query_selector("main")
            or page.query_selector("body")
        )
        if main_el:
            body_text = main_el.inner_text().strip()[:3000]

        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title=title,
            raw_description=body_text[:500] if body_text else None,
            raw_data={"title": title, "description": body_text, "url": url},
        )

    # ── httpx 降级方案 ──────────────────────────────

    async def _fetch_list_via_httpx_async(self) -> list[str]:
        """httpx 降级：从 SSR HTML 提取链接"""
        urls: list[str] = []
        try:
            resp = await self._safe_get(self.base_url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select('a[href*="/v/"]'):
                href = a.get("href", "")
                if href and "/v/" in href:
                    full_url = href if href.startswith("http") else f"https://www.saikr.com{href}"
                    if full_url not in urls:
                        urls.append(full_url)
        except Exception as e:
            logger.warning(f"[{self.platform_name}] httpx 列表降级失败: {e}")
        return urls

    async def _fetch_detail_via_httpx_async(self, url: str) -> CrawlResult:
        """httpx 降级：获取基础 HTML"""
        try:
            resp = await self._safe_get(url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            title_el = soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            body = soup.select_one(".detail-content") or soup.select_one("main") or soup.select_one("body")
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


saikr_crawler = SaiKrCrawler()
