"""
CompeteHub (AI赛事通) 爬虫 — 通过 CloakBrowser 渲染 SSR 页面
网站: https://www.competehub.com/competitions
技术: Next.js SSR + RSC payload，数据嵌入 self.__next_f.push()
"""

import json
import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult

logger = logging.getLogger(__name__)


class CompeteHubCrawler(BaseCrawler):
    platform_name = "competehub"
    base_url = "https://www.competehub.com/competitions"

    async def fetch_list(self) -> list[str]:
        """用 CloakBrowser 渲染列表页，提取竞赛链接"""
        # CloakBrowser 是同步 API，需要在线程中运行
        import asyncio
        urls = await asyncio.to_thread(self._sync_fetch_list)
        return urls

    def _sync_fetch_list(self) -> list[str]:
        """同步方法：用 CloakBrowser 渲染页面"""
        from cloakbrowser import CloakBrowser

        urls = []
        browser = None
        try:
            browser = CloakBrowser(headless=True)
            page = browser.new_page()

            for page_num in range(1, 3):  # 爬2页
                list_url = f"{self.base_url}?page={page_num}" if page_num > 1 else self.base_url
                page.goto(list_url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)

                # 提取竞赛链接
                links = page.query_selector_all('a[href*="/competitions/"]')
                for link in links:
                    href = link.get_attribute("href") or ""
                    if href and "/competitions/" in href and href not in urls:
                        full_url = href if href.startswith("http") else f"https://www.competehub.com{href}"
                        urls.append(full_url)

                logger.info(f"[{self.platform_name}] 第{page_num}页获取 {len(links)} 个链接")

        except Exception as e:
            logger.error(f"[{self.platform_name}] CloakBrowser 列表爬取失败: {e}")
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """用 CloakBrowser 渲染详情页"""
        import asyncio
        return await asyncio.to_thread(self._sync_fetch_detail, url)

    def _sync_fetch_detail(self, url: str) -> CrawlResult:
        """同步方法：渲染详情页并提取数据"""
        from cloakbrowser import CloakBrowser

        browser = None
        try:
            browser = CloakBrowser(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # 提取页面文本内容
            title_el = page.query_selector("h1")
            title = title_el.inner_text().strip() if title_el else ""

            # 提取页面主要内容
            body_text = ""
            main_el = page.query_selector("main") or page.query_selector("article") or page.query_selector("body")
            if main_el:
                body_text = main_el.inner_text().strip()[:3000]

            # 尝试从 Next.js RSC payload 中提取结构化数据
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

    def _extract_next_data(self, page, url: str) -> dict:
        """从 Next.js RSC payload 中提取数据"""
        data = {}
        try:
            # 尝试获取 __NEXT_DATA__ (传统 SSR)
            next_data_script = page.query_selector('script#__NEXT_DATA__')
            if next_data_script:
                content = next_data_script.inner_text()
                parsed = json.loads(content)
                props = parsed.get("props", {}).get("pageProps", {})
                data.update(props)
                return data

            # 尝试从 self.__next_f.push() 中提取 (RSC)
            scripts = page.query_selector_all('script')
            for script in scripts:
                content = script.inner_text()
                if "__next_f.push" in content:
                    # 提取 JSON 片段
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


competehub_crawler = CompeteHubCrawler()
