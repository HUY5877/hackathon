"""
Devpost 爬虫 — 全球最大黑客松平台
网站: https://devpost.com/hackathons
技术: SSR + 分页查询参数，HTML 可直接解析

Devpost 列表页 URL 格式：
    https://devpost.com/hackathons?status=upcoming&open-to=online
详情页 URL 格式：
    https://devpost.com/hackathons/<slug>
"""

import logging
import re

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError

logger = logging.getLogger(__name__)


class DevpostCrawler(BaseCrawler):
    platform_name = "devpost"
    base_url = "https://devpost.com/hackathons"

    async def fetch_list(self) -> list[str]:
        """抓取 Devpost 黑客松列表页，提取详情链接"""
        urls: list[str] = []
        # 抓取 upcoming + open 状态，分页
        for page in range(1, 4):
            try:
                resp = await self._safe_get(
                    self.base_url,
                    params={
                        "status": "upcoming" if page == 1 else "open",
                        "page": page,
                    },
                )
                page_urls = self._parse_list_html(resp.text)
                if not page_urls:
                    logger.info(f"[{self.platform_name}] 第 {page} 页无更多结果，停止")
                    break
                for u in page_urls:
                    if u not in urls:
                        urls.append(u)
                logger.info(f"[{self.platform_name}] 第 {page} 页获取 {len(page_urls)} 个链接")
            except CrawlerError as e:
                logger.error(f"[{self.platform_name}] 列表第 {page} 页失败: {e}")
                break
        return urls

    def _parse_list_html(self, html: str) -> list[str]:
        """从列表页 HTML 提取详情链接"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        # Devpost 卡片链接：a[href*="/hackathons/"] 但排除 /hackathons 本身
        for a in soup.select('a[href*="/hackathons/"]'):
            href = a.get("href", "")
            if not href:
                continue
            # 支持绝对路径 https://devpost.com/hackathons/<slug> 和相对路径 /hackathons/<slug>
            match = re.match(r"(?:https?://devpost\.com)?/hackathons/([^/?#]+)", href)
            if match:
                slug = match.group(1)
                full_url = f"https://devpost.com/hackathons/{slug}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取 Devpost 详情页"""
        try:
            resp = await self._safe_get(url)
            raw_data = self._parse_detail_html(resp.text, url)
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=raw_data.get("title", ""),
                raw_description=(raw_data.get("description", "") or "")[:500],
                raw_data=raw_data,
                image_urls=raw_data.get("image_urls", []),  # ← 新增：图片 URL
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
        """从详情页 HTML 提取结构化数据"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        data: dict = {"url": url}

        # 标题
        title_el = soup.select_one("h1") or soup.select_one("#hackathon-title")
        if title_el:
            data["title"] = title_el.get_text(strip=True)

        # 描述/摘要
        desc_el = (
            soup.select_one(".hackathon-description")
            or soup.select_one("[class*='description']")
            or soup.select_one("main p")
        )
        if desc_el:
            data["description"] = desc_el.get_text(strip=True)[:2000]

        # 奖金
        prize_el = soup.select_one("[class*='prize']") or soup.select_one("#prize")
        if prize_el:
            data["prize"] = prize_el.get_text(strip=True)

        # 时间信息
        for el in soup.select("[class*='date'], [class*='time'], time"):
            text = el.get_text(strip=True)
            if not text:
                continue
            if "start" in (el.get("class") or []) or "begins" in text.lower():
                data["start_date"] = text
            elif "end" in (el.get("class") or []) or "ends" in text.lower():
                data["end_date"] = text
            elif "registration" in text.lower() or "deadline" in text.lower():
                data["signup_end"] = text

        # 地点
        location_el = soup.select_one("[class*='location']") or soup.select_one("[class*='venue']")
        if location_el:
            data["location"] = location_el.get_text(strip=True)

        # 模式（online/offline/in-person）
        body_text = soup.get_text(" ", strip=True).lower()
        if "online" in body_text and "in-person" in body_text:
            data["mode"] = "hybrid"
        elif "online" in body_text:
            data["mode"] = "online"
        elif "in-person" in body_text:
            data["mode"] = "offline"

        # 标签/赛道
        tags: list[str] = []
        for el in soup.select("[class*='tag'], [class*='track'], [class*='badge']"):
            text = el.get_text(strip=True)
            if text and len(text) < 50 and text not in tags:
                tags.append(text)
        if tags:
            data["tracks"] = tags

        # 主办方
        organizer_el = soup.select_one("[class*='organizer']") or soup.select_one("[class*='host']")
        if organizer_el:
            data["organizer"] = organizer_el.get_text(strip=True)

        # 参与人数
        participants_el = soup.select_one("[class*='participant']")
        if participants_el:
            text = participants_el.get_text(strip=True)
            nums = re.findall(r"[\d,]+", text)
            if nums:
                data["participants_count"] = int(nums[0].replace(",", ""))

        # ── 提取图片 ─────────────────────────────
        image_urls: list[str] = []

        # 1. Open Graph 封面图（最标准、最可靠）
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image:
            img_url = og_image.get("content")
            if img_url:
                data["cover_image"] = img_url
                image_urls.append(img_url)

        # 2. 备选：Twitter Card 图
        if not data.get("cover_image"):
            tw_image = soup.select_one('meta[name="twitter:image"]')
            if tw_image:
                img_url = tw_image.get("content")
                if img_url:
                    data["cover_image"] = img_url
                    image_urls.append(img_url)

        # 3. 收集页面中所有有效图片
        for img in soup.select("img"):
            src = img.get("src") or img.get("data-src")
            if src and src.startswith("http"):
                # 过滤掉头像、小图标等无关图片
                width = img.get("width")
                if width:
                    try:
                        if int(width) < 80:
                            continue  # 跳过小图标
                    except ValueError:
                        pass
                if src not in image_urls:
                    image_urls.append(src)

        data["image_urls"] = image_urls

        return data


devpost_crawler = DevpostCrawler()
