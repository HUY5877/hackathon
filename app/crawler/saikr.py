"""
赛氪 (SaiKr) 爬虫 — 国内大学生竞赛信息平台
网站: https://www.saikr.com/vs
技术: SSR 页面，可用 CloakBrowser 渲染
"""

import json
import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult

logger = logging.getLogger(__name__)


class SaiKrCrawler(BaseCrawler):
    platform_name = "saikr"
    base_url = "https://www.saikr.com/vs"

    async def fetch_list(self) -> list[str]:
        import asyncio
        return await asyncio.to_thread(self._sync_fetch_list)

    def _sync_fetch_list(self) -> list[str]:
        from cloakbrowser import CloakBrowser

        urls = []
        browser = None
        try:
            browser = CloakBrowser(headless=True)
            page = browser.new_page()
            page.goto(self.base_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            links = page.query_selector_all('a[href*="/v/"]')
            for link in links:
                href = link.get_attribute("href") or ""
                if href and "/v/" in href:
                    full_url = href if href.startswith("http") else f"https://www.saikr.com{href}"
                    if full_url not in urls:
                        urls.append(full_url)

            logger.info(f"[{self.platform_name}] 列表页获取 {len(urls)} 个链接")
        except Exception as e:
            logger.error(f"[{self.platform_name}] 列表爬取失败: {e}")
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        import asyncio
        return await asyncio.to_thread(self._sync_fetch_detail, url)

    def _sync_fetch_detail(self, url: str) -> CrawlResult:
        from cloakbrowser import CloakBrowser

        browser = None
        try:
            browser = CloakBrowser(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            title_el = page.query_selector("h1")
            title = title_el.inner_text().strip() if title_el else ""

            body_text = ""
            main_el = page.query_selector(".detail-content") or page.query_selector("main") or page.query_selector("body")
            if main_el:
                body_text = main_el.inner_text().strip()[:3000]

            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=title,
                raw_description=body_text[:500] if body_text else None,
                raw_data={"title": title, "description": body_text, "url": url},
            )
        except Exception as e:
            logger.error(f"[{self.platform_name}] 详情爬取失败 {url}: {e}")
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title="",
                raw_data={"url": url, "error": str(e)},
            )
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass


saikr_crawler = SaiKrCrawler()
