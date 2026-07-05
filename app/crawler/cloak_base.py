"""CloakBrowser 爬虫基类 — 使用 CloakBrowser 绕过 WAF

特性：
- CloakBrowser 自动启用 stealth 指纹，绕过 AWS WAF 等反爬
- 浏览器实例复用（避免每次抓取都启动新浏览器）
- CloakBrowser 不可用时优雅降级到 httpx
"""

import asyncio
import logging
import threading

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError

logger = logging.getLogger(__name__)


class CloakBrowserBaseCrawler(BaseCrawler):
    """CloakBrowser 爬虫基类

    使用 CloakBrowser 的 stealth 功能绕过 WAF，
    子类只需实现 _parse_list_html / _parse_detail_html。
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._browser = None
        self._browser_lock = threading.Lock()
        self._cloak_available: bool | None = None

    def _check_cloak_available(self) -> bool:
        """检测 CloakBrowser 是否可用（惰性检测）"""
        if self._cloak_available is not None:
            return self._cloak_available
        try:
            import cloakbrowser  # noqa: F401
            self._cloak_available = True
        except ImportError:
            logger.warning(
                f"[{self.platform_name}] CloakBrowser 未安装，将降级到 httpx"
            )
            self._cloak_available = False
        return self._cloak_available

    async def _get_browser(self):
        """获取复用的 CloakBrowser 实例（线程安全）"""
        if not self._check_cloak_available():
            return None
        with self._browser_lock:
            if self._browser is None:
                try:
                    import cloakbrowser
                    self._browser = await cloakbrowser.launch_async(
                        headless=True,
                        stealth_args=True,  # 启用 stealth 指纹
                    )
                    logger.info(f"[{self.platform_name}] 启动 CloakBrowser 实例")
                except Exception as e:
                    logger.error(f"[{self.platform_name}] CloakBrowser 启动失败: {e}")
                    self._cloak_available = False
                    return None
        return self._browser

    async def _fetch_with_browser(self, url: str, scroll: bool = False) -> str:
        """用 CloakBrowser 获取页面 HTML

        Args:
            url: 目标 URL
            scroll: 是否滚动页面触发懒加载
        """
        browser = await self._get_browser()
        if browser is None:
            raise CrawlerError("CloakBrowser 不可用")

        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)  # 等 JS 渲染

            if scroll:
                for _ in range(5):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)

            html = await page.content()
            return html
        finally:
            await page.close()

    async def close(self):
        """关闭浏览器实例"""
        with self._browser_lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
        await super().close()

    # ── 子类覆盖这些方法 ──────────────────────────────

    def _parse_list_html(self, html: str) -> list[str]:
        """从列表页 HTML 提取 URL，子类实现"""
        raise NotImplementedError

    def _parse_detail_html(self, html: str, url: str) -> dict:
        """从详情页 HTML 提取数据，子类实现"""
        raise NotImplementedError

    async def _fetch_list_via_httpx_async(self) -> list[str]:
        """httpx 降级方案，子类可覆盖"""
        logger.info(f"[{self.platform_name}] 使用 httpx 降级抓取列表")
        return []

    async def _fetch_detail_via_httpx_async(self, url: str) -> CrawlResult:
        """httpx 降级方案，子类可覆盖"""
        logger.info(f"[{self.platform_name}] 使用 httpx 降级抓取详情 {url}")
        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title="",
            success=False,
            error_message="CloakBrowser 不可用且无 httpx 降级方案",
        )

    # ── 公开接口 ─────────────────────────────────────

    async def fetch_list(self) -> list[str]:
        """自动选择 CloakBrowser 或 httpx 抓取列表"""
        if not self._check_cloak_available():
            return await self._fetch_list_via_httpx_async()

        try:
            html = await self._fetch_with_browser(self.base_url, scroll=True)
            urls = self._parse_list_html(html)
            logger.info(f"[{self.platform_name}] CloakBrowser 获取 {len(urls)} 个链接")
            return urls
        except Exception as e:
            logger.error(f"[{self.platform_name}] CloakBrowser 列表抓取失败，尝试 httpx 降级: {e}")
            return await self._fetch_list_via_httpx_async()

    async def fetch_detail(self, url: str) -> CrawlResult:
        """自动选择 CloakBrowser 或 httpx 抓取详情"""
        if not self._check_cloak_available():
            return await self._fetch_detail_via_httpx_async(url)

        try:
            html = await self._fetch_with_browser(url, scroll=False)
            raw_data = self._parse_detail_html(html, url)
            return CrawlResult(
                source_platform=self.platform_name,
                source_url=url,
                raw_title=raw_data.get("title", ""),
                raw_description=(raw_data.get("description", "") or "")[:500],
                raw_data=raw_data,
                image_urls=raw_data.get("image_urls", []),
            )
        except Exception as e:
            logger.error(f"[{self.platform_name}] CloakBrowser 详情抓取失败 {url}，尝试 httpx 降级: {e}")
            return await self._fetch_detail_via_httpx_async(url)
