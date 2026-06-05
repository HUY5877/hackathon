"""
活动行 (Huodongxing) 爬虫 — 国内活动发布平台
网站: https://www.huodongxing.com
技术: SSR + REST API
"""

import logging

import httpx

from app.crawler.base import BaseCrawler, CrawlResult

logger = logging.getLogger(__name__)


class HuodongxingCrawler(BaseCrawler):
    platform_name = "huodongxing"
    base_url = "https://www.huodongxing.com"
    search_url = "https://www.huodongxing.com/search"

    async def fetch_list(self) -> list[str]:
        """搜索黑客松相关活动"""
        urls = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html",
                }
                resp = await client.get(
                    self.search_url,
                    params={"keyword": "黑客松", "city": "全部"},
                    headers=headers,
                )
                resp.raise_for_status()

                # 从 HTML 中提取活动链接
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.select('a[href*="/event/"]'):
                    href = a.get("href", "")
                    if "/event/" in href:
                        full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                        if full_url not in urls:
                            urls.append(full_url)

                logger.info(f"[{self.platform_name}] 搜索获取 {len(urls)} 个链接")
            except Exception as e:
                logger.error(f"[{self.platform_name}] 搜索失败: {e}")

        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取活动详情页"""
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")

                title = ""
                title_el = soup.select_one("h1") or soup.select_one(".event-title")
                if title_el:
                    title = title_el.get_text(strip=True)

                # 提取页面文本
                body_text = ""
                content_el = soup.select_one(".event-detail") or soup.select_one("main") or soup.select_one("body")
                if content_el:
                    body_text = content_el.get_text(strip=True)[:3000]

                # 提取时间、地点等
                raw_data = {"title": title, "description": body_text, "url": url}

                # 尝试提取结构化字段
                for item in soup.select(".info-item, .detail-item"):
                    text = item.get_text(strip=True)
                    if "时间" in text:
                        raw_data["date_info"] = text
                    elif "地点" in text or "地址" in text:
                        raw_data["location"] = text.replace("地点", "").replace("地址", "").strip()

                return CrawlResult(
                    source_platform=self.platform_name,
                    source_url=url,
                    raw_title=title,
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


huodongxing_crawler = HuodongxingCrawler()
