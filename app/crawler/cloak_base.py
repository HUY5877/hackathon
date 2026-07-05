"""
CloakBrowser 爬虫基类 — 统一浏览器生命周期管理

特性：
- 浏览器实例复用（避免每次抓取都启动新浏览器）
- CloakBrowser 不可用时优雅降级到 httpx
- 统一的页面操作上下文管理器
- 超时与异常处理
"""

import logging
import threading
from contextlib import contextmanager
from typing import Generator

from app.crawler.base import BaseCrawler, CrawlResult, CrawlerError, BlockedError

logger = logging.getLogger(__name__)


class CloakBrowserBaseCrawler(BaseCrawler):
    """CloakBrowser 爬虫基类

    子类只需实现 _fetch_list_with_page / _fetch_detail_with_page，
    无需关心浏览器启动/关闭/降级逻辑。
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._browser = None
        self._browser_lock = threading.Lock()
        self._cloak_available: bool | None = None  # None=未检测, True/False=已检测

    def _check_cloak_available(self) -> bool:
        """检测 CloakBrowser 是否可用（惰性检测，只检测一次）"""
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

    def _get_browser(self):
        """获取复用的浏览器实例（线程安全）"""
        if not self._check_cloak_available():
            return None
        with self._browser_lock:
            if self._browser is None:
                try:
                    from cloakbrowser import CloakBrowser
                    self._browser = CloakBrowser(headless=True)
                    logger.info(f"[{self.platform_name}] 启动 CloakBrowser 实例")
                except Exception as e:
                    logger.error(f"[{self.platform_name}] CloakBrowser 启动失败: {e}")
                    self._cloak_available = False
                    return None
        return self._browser

    @contextmanager
    def _new_page(self, timeout: int = 30000):
        """页面上下文管理器，自动关闭页面

        Usage:
            with self._new_page() as page:
                page.goto(url)
                ...
        """
        browser = self._get_browser()
        if browser is None:
            raise CrawlerError("CloakBrowser 不可用")
        page = None
        try:
            page = browser.new_page()
            page.set_default_timeout(timeout)
            yield page
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def _safe_goto(self, page, url: str, wait_until: str = "networkidle", timeout: int = 30000) -> bool:
        """安全导航，返回是否成功"""
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            page.wait_for_timeout(2000)
            return True
        except Exception as e:
            logger.warning(f"[{self.platform_name}] 页面导航失败 {url}: {e}")
            return False

    def _extract_text(self, page, selector: str) -> str:
        """安全提取元素文本"""
        try:
            el = page.query_selector(selector)
            if el:
                return el.inner_text().strip()
        except Exception as e:
            logger.debug(f"[{self.platform_name}] 提取 {selector} 失败: {e}")
        return ""

    def _extract_all_texts(self, page, selector: str, max_len: int = 50) -> list[str]:
        """安全提取多个元素文本"""
        results: list[str] = []
        try:
            els = page.query_selector_all(selector)
            for el in els:
                text = el.inner_text().strip()
                if text and len(text) < max_len and text not in results:
                    results.append(text)
        except Exception as e:
            logger.debug(f"[{self.platform_name}] 提取 {selector} 列表失败: {e}")
        return results

    async def close(self):
        """关闭浏览器实例和 HTTP 客户端（异步，与基类签名一致）"""
        with self._browser_lock:
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None
        # 调用基类的 close 关闭 HTTP 客户端
        await super().close()

    async def aclose(self):
        """异步关闭的别名（向后兼容）"""
        await self.close()

    # ── 子类实现这两个方法 ──────────────────────────────

    def _fetch_list_with_page(self, page) -> list[str]:
        """用 CloakBrowser 页面抓取列表，子类实现"""
        raise NotImplementedError

    def _fetch_detail_with_page(self, page, url: str) -> CrawlResult:
        """用 CloakBrowser 页面抓取详情，子类实现"""
        raise NotImplementedError

    async def _fetch_list_via_httpx_async(self) -> list[str]:
        """httpx 降级方案（异步），子类可覆盖"""
        logger.info(f"[{self.platform_name}] 使用 httpx 降级抓取列表")
        return []

    async def _fetch_detail_via_httpx_async(self, url: str) -> CrawlResult:
        """httpx 降级方案（异步），子类可覆盖"""
        logger.info(f"[{self.platform_name}] 使用 httpx 降级抓取详情 {url}")
        return CrawlResult(
            source_platform=self.platform_name,
            source_url=url,
            raw_title="",
            success=False,
            error_message="CloakBrowser 不可用且无 httpx 降级方案",
        )

    # ── 公开接口（自动选择 CloakBrowser 或 httpx）─────

    async def fetch_list(self) -> list[str]:
        """自动选择 CloakBrowser 或 httpx 抓取列表"""
        import asyncio

        if not self._check_cloak_available():
            return await self._fetch_list_via_httpx_async()

        try:
            return await asyncio.to_thread(self._fetch_list_with_browser)
        except Exception as e:
            logger.error(f"[{self.platform_name}] CloakBrowser 列表抓取失败，尝试 httpx 降级: {e}")
            return await self._fetch_list_via_httpx_async()

    def _fetch_list_with_browser(self) -> list[str]:
        """用 CloakBrowser 抓取列表（含异常处理）"""
        urls: list[str] = []
        with self._new_page() as page:
            urls = self._fetch_list_with_page(page)
        return urls

    async def fetch_detail(self, url: str) -> CrawlResult:
        """自动选择 CloakBrowser 或 httpx 抓取详情"""
        import asyncio

        if not self._check_cloak_available():
            return await self._fetch_detail_via_httpx_async(url)

        try:
            return await asyncio.to_thread(self._fetch_detail_with_browser, url)
        except Exception as e:
            logger.error(f"[{self.platform_name}] CloakBrowser 详情抓取失败 {url}，尝试 httpx 降级: {e}")
            return await self._fetch_detail_via_httpx_async(url)

    def _fetch_detail_with_browser(self, url: str) -> CrawlResult:
        """用 CloakBrowser 抓取详情（含异常处理）"""
        with self._new_page() as page:
            return self._fetch_detail_with_page(page, url)
