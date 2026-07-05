"""
活动行 (Huodongxing) 爬虫 — 国内活动发布平台
网站: https://www.huodongxing.com
技术: SSR + 搜索接口，HTML 可直接解析

改进点：
- 多关键词搜索（黑客松/黑客马拉松/hackathon/编程竞赛）
- 结构化字段提取（时间/地点/主办方/费用/报名状态）
- 使用基类的 _safe_get 重试机制
"""

import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError

logger = logging.getLogger(__name__)

# 搜索关键词：覆盖中英文与同义词
SEARCH_KEYWORDS = ["黑客松", "黑客马拉松", "hackathon", "编程竞赛", "创客马拉松"]


class HuodongxingCrawler(BaseCrawler):
    platform_name = "huodongxing"
    base_url = "https://www.huodongxing.com"
    search_url = "https://www.huodongxing.com/search"

    async def fetch_list(self) -> list[str]:
        """多关键词搜索，合并去重"""
        urls: list[str] = []
        for keyword in SEARCH_KEYWORDS:
            try:
                resp = await self._safe_get(
                    self.search_url,
                    params={"keyword": keyword, "city": "全部"},
                )
                page_urls = self._parse_search_html(resp.text)
                new_count = 0
                for u in page_urls:
                    if u not in urls:
                        urls.append(u)
                        new_count += 1
                logger.info(f"[{self.platform_name}] 关键词 '{keyword}' 获取 {len(page_urls)} 条 (新增 {new_count})")
                if not page_urls:
                    # 关键词无结果可能是被反爬，继续尝试下一个
                    continue
            except CrawlerError as e:
                logger.warning(f"[{self.platform_name}] 关键词 '{keyword}' 搜索失败: {e}")
                continue
        return urls

    def _parse_search_html(self, html: str) -> list[str]:
        """从搜索结果 HTML 提取活动链接"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        # 活动行活动链接格式：/event/<id>.html 或 /event/<id>
        for a in soup.select('a[href*="/event/"]'):
            href = a.get("href", "")
            if not href:
                continue
            # 仅保留详情页（/event/<id>），排除其他子路径
            match = re.search(r"/event/(\d+)", href)
            if match:
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取活动详情页，结构化提取字段"""
        try:
            resp = await self._safe_get(url)
            raw_data = self._parse_detail_html(resp.text, url)
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=raw_data.get("title", ""),
                raw_description=(raw_data.get("description", "") or "")[:500],
                raw_data=raw_data,
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
        """从活动详情页提取结构化数据"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        data: dict = {"url": url}

        # 标题
        title_el = (
            soup.select_one("h1")
            or soup.select_one(".event-title")
            or soup.select_one(".title")
        )
        if title_el:
            data["title"] = title_el.get_text(strip=True)

        # 正文内容
        body_text = ""
        content_el = (
            soup.select_one(".event-detail")
            or soup.select_one(".detail-content")
            or soup.select_one(".content")
            or soup.select_one("main")
            or soup.select_one("body")
        )
        if content_el:
            body_text = content_el.get_text(" ", strip=True)[:3000]
            data["description"] = body_text

        # 结构化字段提取：活动行通常用 .info-item / .detail-item / <li> 展示元信息
        info_map = {
            "时间": ["start_date", "end_date"],
            "开始": ["start_date"],
            "结束": ["end_date"],
            "地点": ["location"],
            "地址": ["location"],
            "城市": ["city"],
            "主办方": ["organizer"],
            "主办": ["organizer"],
            "费用": ["price"],
            "票价": ["price"],
            "报名": ["signup_end"],
            "截止": ["signup_end"],
        }

        for item in soup.select(".info-item, .detail-item, .info-row, li, dt"):
            text = item.get_text(" ", strip=True)
            if not text:
                continue
            # 匹配 "标签：值" 或 "标签 值" 格式
            for label, fields in info_map.items():
                if label in text:
                    # 提取标签后的值
                    value = re.sub(rf"^.*{label}\s*[:：]?\s*", "", text).strip()
                    if value and len(value) < 200:
                        for field in fields:
                            if field not in data or not data[field]:
                                data[field] = value
                        break

        # 模式判断
        if data.get("location"):
            loc = data["location"].lower()
            if "线上" in data["location"] or "online" in loc:
                data["mode"] = "online"
            elif "线下" in data["location"] or "offline" in loc:
                data["mode"] = "offline"
            else:
                data["mode"] = "offline"  # 活动行默认线下
        else:
            data["mode"] = "online"

        # 标签
        tags: list[str] = []
        for el in soup.select(".tag, .label, [class*='tag'], [class*='badge']"):
            text = el.get_text(strip=True)
            if text and len(text) < 30 and text not in tags:
                tags.append(text)
        if tags:
            data["tracks"] = tags

        # 参与人数
        participants_el = soup.select_one("[class*='participant'], [class*='attend']")
        if participants_el:
            text = participants_el.get_text(strip=True)
            nums = re.findall(r"[\d,]+", text)
            if nums:
                data["participants_count"] = int(nums[0].replace(",", ""))

        # 报名状态
        status_el = soup.select_one("[class*='status'], .btn-status")
        if status_el:
            status_text = status_el.get_text(strip=True)
            if "报名中" in status_text or "进行中" in status_text:
                data["status"] = "open"
            elif "已结束" in status_text:
                data["status"] = "ended"
            elif "即将开始" in status_text:
                data["status"] = "upcoming"

        return data


huodongxing_crawler = HuodongxingCrawler()
