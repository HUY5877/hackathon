"""
CompeteHub (AI赛事通) 爬虫 — 通过 CloakBrowser 渲染 SSR 页面
网站: https://www.competehub.com/competitions
技术: Next.js SSR + RSC payload，数据嵌入 self.__next_f.push()
"""

import json
import logging
import re

from app.crawler.base import CrawlResult
from app.crawler.cloak_base import CloakBrowserBaseCrawler

logger = logging.getLogger(__name__)


class CompeteHubCrawler(CloakBrowserBaseCrawler):
    platform_name = "competehub"
    base_url = "https://www.competehub.com/competitions"

    def _fetch_list_with_page(self, page) -> list[str]:
        """用 CloakBrowser 渲染列表页，提取竞赛链接"""
        urls: list[str] = []
        for page_num in range(1, 3):
            list_url = f"{self.base_url}?page={page_num}" if page_num > 1 else self.base_url
            if not self._safe_goto(page, list_url, timeout=30000):
                continue

            links = page.query_selector_all('a[href*="/competitions/"]')
            new_count = 0
            for link in links:
                href = link.get_attribute("href") or ""
                if href and "/competitions/" in href and href not in urls:
                    full_url = href if href.startswith("http") else f"https://www.competehub.com{href}"
                    if full_url not in urls:
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

        raw_data = self._extract_next_data(page, url)
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

    def _extract_next_data(self, page, url: str) -> dict:
        """从 Next.js RSC payload 中提取数据"""
        data: dict = {}
        try:
            next_data_script = page.query_selector('script#__NEXT_DATA__')
            if next_data_script:
                content = next_data_script.inner_text()
                parsed = json.loads(content)
                props = parsed.get("props", {}).get("pageProps", {})
                data.update(props)
                return data

            scripts = page.query_selector_all('script')
            for script in scripts:
                content = script.inner_text()
                if "__next_f.push" in content:
                    matches = re.findall(r'"((?:[^"\\]|\\.)*)"', content)
                    for match in matches:
                        if len(match) > 50:
                            try:
                                fragment = json.loads(f'"{match}"')
                                if isinstance(fragment, str) and "{" in fragment:
                                    parsed = json.loads(fragment)
                                    if isinstance(parsed, dict):
                                        data.update(parsed)
                            except (json.JSONDecodeError, ValueError):
                                continue
        except Exception as e:
            logger.debug(f"[{self.platform_name}] Next.js 数据提取失败: {e}")
        return data

    # ── httpx 降级方案 ──────────────────────────────

    async def _fetch_list_via_httpx_async(self) -> list[str]:
        """httpx 降级：尝试从 SSR HTML 提取链接"""
        urls: list[str] = []
        try:
            resp = await self._safe_get(self.base_url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select('a[href*="/competitions/"]'):
                href = a.get("href", "")
                if href and "/competitions/" in href:
                    full_url = href if href.startswith("http") else f"https://www.competehub.com{href}"
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


competehub_crawler = CompeteHubCrawler()
