"""
天池 (Tianchi) 爬虫 — 阿里云天池大数据竞赛平台
网站: https://tianchi.aliyun.com/competition
技术: 前端渲染，REST API 可用
"""

import logging

import httpx

from app.crawler.base import BaseCrawler, CrawlResult

logger = logging.getLogger(__name__)


class TianchiCrawler(BaseCrawler):
    platform_name = "tianchi"
    base_url = "https://tianchi.aliyun.com/competition"
    api_base = "https://tianchi.aliyun.com/api/competition/list"

    async def fetch_list(self) -> list[str]:
        """通过天池 API 获取竞赛列表"""
        urls = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    self.api_base,
                    params={"page": 1, "pageSize": 20, "status": "all"},
                )
                resp.raise_for_status()
                data = resp.json()

                items = data.get("data", {}).get("list", []) if isinstance(data, dict) else []
                for item in items:
                    comp_id = item.get("competitionId") or item.get("id", "")
                    if comp_id:
                        urls.append(f"https://tianchi.aliyun.com/competition/entrance/{comp_id}/introduction")

                logger.info(f"[{self.platform_name}] 列表获取 {len(urls)} 条")
            except Exception as e:
                logger.error(f"[{self.platform_name}] 列表爬取失败: {e}")

        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """通过 API 获取竞赛详情"""
        # 从 URL 提取 ID
        import re
        match = re.search(r"/entrance/(\d+)", url)
        comp_id = match.group(1) if match else ""

        raw_data = {"url": url, "title": ""}

        if comp_id:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                try:
                    resp = await client.get(
                        f"https://tianchi.aliyun.com/api/competition/detail",
                        params={"competitionId": comp_id},
                    )
                    resp.raise_for_status()
                    data = resp.json()
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
                except Exception as e:
                    logger.error(f"[{self.platform_name}] 详情爬取失败 {url}: {e}")
                    raw_data["error"] = str(e)

        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title=raw_data.get("title", ""),
            raw_description=raw_data.get("description", "")[:500],
            raw_data=raw_data,
        )


tianchi_crawler = TianchiCrawler()
