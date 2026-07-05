"""
天池 (Tianchi) 爬虫 — 阿里云天池大数据竞赛平台
网站: https://tianchi.aliyun.com/competition
技术: 前端渲染，REST API 可用
"""

import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError, ParseError

logger = logging.getLogger(__name__)


class TianchiCrawler(BaseCrawler):
    platform_name = "tianchi"
    base_url = "https://tianchi.aliyun.com/competition"
    # 多个候选 API 端点，按优先级尝试
    LIST_API_CANDIDATES = [
        "https://tianchi.aliyun.com/api/competition/list",
        "https://tianchi.aliyun.com/api/notice/competitionList",
    ]
    DETAIL_API = "https://tianchi.aliyun.com/api/competition/detail"

    async def fetch_list(self) -> list[str]:
        """通过天池 API 获取竞赛列表，多端点回退"""
        urls: list[str] = []
        for api_url in self.LIST_API_CANDIDATES:
            try:
                resp = await self._safe_get(
                    api_url,
                    params={"page": 1, "pageSize": 20, "status": "all"},
                )
                data = self._safe_parse_json(resp.text)
                items = self._extract_items(data)
                if items:
                    for item in items:
                        comp_id = item.get("competitionId") or item.get("id", "")
                        if comp_id:
                            urls.append(
                                f"https://tianchi.aliyun.com/competition/entrance/{comp_id}/introduction"
                            )
                    logger.info(f"[{self.platform_name}] {api_url} 获取 {len(urls)} 条")
                    return urls
            except CrawlerError as e:
                logger.warning(f"[{self.platform_name}] API {api_url} 失败: {e}")
                continue

        # 全部 API 失败时回退到 HTML 列表页
        logger.info(f"[{self.platform_name}] API 全部失败，回退到 HTML 抓取")
        return await self._fetch_list_from_html()

    def _extract_items(self, data: dict) -> list[dict]:
        """从不同 API 响应结构中提取竞赛列表"""
        if not isinstance(data, dict):
            return []
        # 常见结构：data.data.list / data.data / data.list
        for path in [("data", "list"), ("data", "data", "list"), ("list",)]:
            node = data
            try:
                for key in path:
                    node = node[key]
                if isinstance(node, list):
                    return node
            except (KeyError, TypeError):
                continue
        return []

    async def _fetch_list_from_html(self) -> list[str]:
        """从 HTML 列表页提取链接（API 不可用时的回退方案）"""
        urls: list[str] = []
        try:
            resp = await self._safe_get(self.base_url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select('a[href*="/competition/entrance/"]'):
                href = a.get("href", "")
                match = re.search(r"/entrance/(\d+)", href)
                if match:
                    comp_id = match.group(1)
                    url = f"https://tianchi.aliyun.com/competition/entrance/{comp_id}/introduction"
                    if url not in urls:
                        urls.append(url)
            logger.info(f"[{self.platform_name}] HTML 列表获取 {len(urls)} 条")
        except CrawlerError as e:
            logger.error(f"[{self.platform_name}] HTML 列表抓取失败: {e}")
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """通过 API 获取竞赛详情，失败时回退到 HTML"""
        match = re.search(r"/entrance/(\d+)", url)
        comp_id = match.group(1) if match else ""

        raw_data: dict = {"url": url, "title": ""}

        if comp_id:
            # 尝试 API
            try:
                resp = await self._safe_get(
                    self.DETAIL_API,
                    params={"competitionId": comp_id},
                )
                data = self._safe_parse_json(resp.text)
                detail = data.get("data", {}) if isinstance(data, dict) else {}
                raw_data = {
                    "title": detail.get("title", ""),
                    "description": detail.get("brief", "") or detail.get("description", ""),
                    "url": url,
                    "start_date": detail.get("startTime", ""),
                    "end_date": detail.get("endTime", ""),
                    "prize": detail.get("prize", ""),
                    "organizer": detail.get("organizer", ""),
                    "mode": detail.get("mode", "online"),
                    "status": detail.get("status", ""),
                    "participants_count": detail.get("participantCount", 0),
                }
                if raw_data["title"]:
                    return self._build_result(url, raw_data)
            except CrawlerError as e:
                logger.warning(f"[{self.platform_name}] 详情 API 失败 {url}: {e}")

            # API 失败或返回空，回退到 HTML
            try:
                raw_data = await self._fetch_detail_from_html(url, raw_data)
            except CrawlerError as e:
                logger.error(f"[{self.platform_name}] 详情 HTML 也失败 {url}: {e}")
                raw_data["error"] = str(e)

        return self._build_result(url, raw_data)

    async def _fetch_detail_from_html(self, url: str, raw_data: dict) -> dict:
        """从 HTML 详情页提取数据"""
        resp = await self._safe_get(url)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")

        title = ""
        title_el = soup.select_one("h1") or soup.select_one(".title")
        if title_el:
            title = title_el.get_text(strip=True)

        body_text = ""
        content_el = (
            soup.select_one(".competition-detail")
            or soup.select_one(".main-content")
            or soup.select_one("main")
            or soup.select_one("body")
        )
        if content_el:
            body_text = content_el.get_text(strip=True)[:3000]

        raw_data.update({
            "title": title or raw_data.get("title", ""),
            "description": body_text,
            "url": url,
        })
        return raw_data

    def _build_result(self, url: str, raw_data: dict) -> CrawlResult:
        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title=raw_data.get("title", ""),
            raw_description=(raw_data.get("description", "") or "")[:500],
            raw_data=raw_data,
        )


tianchi_crawler = TianchiCrawler()
