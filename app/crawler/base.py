"""
爬虫基类 — 定义所有平台爬虫的统一接口
对应架构图：自动化爬虫引擎 (D1)
"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


# ── 异常分类 ──────────────────────────────────────────

class CrawlerError(Exception):
    """爬虫基础异常"""


class NetworkError(CrawlerError):
    """网络层错误（连接超时、DNS 失败等）— 可重试"""


class HTTPStatusError(CrawlerError):
    """HTTP 状态码错误"""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        """5xx 与 429 可重试，4xx 不可重试"""
        return self.status_code >= 500 or self.status_code == 429


class ParseError(CrawlerError):
    """解析错误（HTML/JSON 解析失败）— 不可重试"""


class BlockedError(CrawlerError):
    """被反爬虫拦截（403/验证码）— 不可重试，需切换代理或浏览器"""


# ── 数据结构 ──────────────────────────────────────────

@dataclass
class CrawlResult:
    """单条爬取结果（原始数据，未经 LLM 清洗）"""
    source_platform: str
    source_url: str
    raw_title: str
    raw_description: str | None = None
    raw_data: dict = field(default_factory=dict)
    image_urls: list[str] = field(default_factory=list)  # ← 新增：爬取到的图片 URL
    crawled_at: datetime = field(default_factory=datetime.now)
    # 标记本次抓取是否成功，便于调度器统计
    success: bool = True
    error_message: str | None = None


def crawl_result_validation_error(result: CrawlResult) -> str | None:
    """Return why a crawl result must not enter mapping/persistence.

    Individual crawlers may fail open or return an empty parse after a source
    page changes.  The scheduler uses this as a final data-integrity barrier.
    """
    if not result.success:
        return result.error_message or "detail_fetch_failed"
    if not isinstance(result.raw_title, str) or not result.raw_title.strip():
        return "missing_required_title"
    if not isinstance(result.source_platform, str) or not result.source_platform.strip():
        return "missing_source_platform"
    parsed_url = urlparse(result.source_url or "")
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return "invalid_source_url"
    return None


# ── 重试装饰器 ────────────────────────────────────────

async def retry_async(
    func,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (NetworkError, httpx.TimeoutException, httpx.NetworkError),
    **kwargs,
):
    """带指数退避 + 抖动的异步重试

    Args:
        max_retries: 最大重试次数（不含首次调用）
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟上限
        retryable_exceptions: 可重试的异常类型

    Note:
        如果异常类型在 retryable_exceptions 中，但具有 `retryable` 属性且值为 False，
        则不会重试（用于 HTTPStatusError 区分 4xx/5xx）。
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as e:
            # 检查异常自身的 retryable 属性（如 HTTPStatusError.retryable）
            # 4xx 错误（非 429）不可重试，直接抛出
            if hasattr(e, "retryable") and e.retryable is False:
                logger.debug(f"[retry] 异常标记为不可重试，直接抛出: {e}")
                raise
            last_exc = e
            if attempt == max_retries:
                logger.warning(f"[retry] 达到最大重试次数 {max_retries}: {e}")
                raise
            # 指数退避 + 抖动，避免惊群
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
            logger.info(f"[retry] 第 {attempt + 1}/{max_retries} 次重试，{delay:.1f}s 后重试: {e}")
            await asyncio.sleep(delay)
        except Exception as e:
            # 不可重试异常，直接抛出
            raise
    # 理论不可达
    if last_exc:
        raise last_exc


# ── User-Agent 池 ─────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/537.36",
]


def _pick_user_agent() -> str:
    """随机选择一个 User-Agent"""
    return random.choice(_USER_AGENTS)


# ── 基类 ──────────────────────────────────────────────

def extract_images_from_html(soup, base_url: str = "") -> tuple[str | None, list[str]]:
    """从 BeautifulSoup 解析的 HTML 中提取图片 URL

    Returns:
        (cover_image, image_urls)
        - cover_image: 最佳封面图 URL（OG / Twitter Card 优先）
        - image_urls: 所有有效图片 URL 列表（去重）
    """
    from urllib.parse import urljoin

    image_urls: list[str] = []
    cover_image: str | None = None

    # 1. Open Graph 封面图（最标准、最可靠）
    og_image = soup.select_one('meta[property="og:image"]')
    if og_image:
        img_url = og_image.get("content")
        if img_url:
            full_url = urljoin(base_url, img_url)
            cover_image = full_url
            if full_url not in image_urls:
                image_urls.append(full_url)

    # 2. Twitter Card 图
    if not cover_image:
        tw_image = soup.select_one('meta[name="twitter:image"]')
        if tw_image:
            img_url = tw_image.get("content")
            if img_url:
                full_url = urljoin(base_url, img_url)
                cover_image = full_url
                if full_url not in image_urls:
                    image_urls.append(full_url)

    # 3. 收集页面中所有有效图片（过滤小图标）
    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            full_src = urljoin(base_url, src)
            if full_src.startswith("http") and full_src not in image_urls:
                # 过滤小图标（通过 width 属性或 URL 特征）
                width = img.get("width")
                if width:
                    try:
                        if int(width) < 80:
                            continue
                    except ValueError:
                        pass
                # 过滤常见的小图标/头像/Logo 路径
                src_lower = src.lower()
                if any(k in src_lower for k in ["icon", "avatar", "logo", "favicon", "badge"]):
                    continue
                image_urls.append(full_src)

    return cover_image, image_urls


class BaseCrawler(ABC):
    """爬虫基类

    提供统一的：
    - 重试机制（指数退避 + 抖动，自动识别 4xx 不可重试）
    - 异常分类（NetworkError / HTTPStatusError / ParseError / BlockedError）
    - 请求间延迟（避免触发频控）
    - User-Agent 轮换（启用后每次请求随机 UA）
    - 代理池支持（逗号分隔，轮询使用）
    """

    # 子类必须定义
    platform_name: str = "unknown"
    base_url: str = ""

    def __init__(
        self,
        request_delay: float | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        proxy: str | None = None,
        ua_rotation: bool | None = None,
    ):
        # 从全局配置读取默认值，便于一处配置全局生效
        from app.config import settings
        self.request_delay = request_delay if request_delay is not None else settings.CRAWLER_REQUEST_DELAY
        self.timeout = timeout if timeout is not None else settings.CRAWLER_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else settings.CRAWLER_MAX_RETRIES
        self.ua_rotation = ua_rotation if ua_rotation is not None else settings.CRAWLER_UA_ROTATION

        # 代理池：支持逗号分隔的多个代理，轮询使用
        self._proxy_pool: list[str] = []
        if proxy:
            self._proxy_pool = [p.strip() for p in proxy.split(",") if p.strip()]
        elif settings.CRAWLER_PROXY_POOL:
            self._proxy_pool = [p.strip() for p in settings.CRAWLER_PROXY_POOL.split(",") if p.strip()]
        self._proxy_idx = 0

        self._client: httpx.AsyncClient | None = None

    @abstractmethod
    async def fetch_list(self) -> list[str]:
        """抓取列表页，返回详情页 URL 列表"""
        ...

    @abstractmethod
    async def fetch_detail(self, url: str) -> CrawlResult:
        """抓取详情页，返回原始数据"""
        ...

    # ── HTTP 客户端管理 ──────────────────────────────

    def _current_proxy(self) -> str | None:
        """轮询获取当前代理"""
        if not self._proxy_pool:
            return None
        proxy = self._proxy_pool[self._proxy_idx % len(self._proxy_pool)]
        self._proxy_idx += 1
        return proxy

    def _current_user_agent(self) -> str:
        """获取当前 User-Agent（启用轮换时随机）"""
        if self.ua_rotation:
            return _pick_user_agent()
        from app.config import settings
        return settings.CRAWLER_USER_AGENT

    def _build_client(self, proxy: str | None = None) -> httpx.AsyncClient:
        """构建带默认配置的 httpx 客户端"""
        headers = {
            "User-Agent": self._current_user_agent(),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        kwargs: dict[str, Any] = {
            "timeout": self.timeout,
            "follow_redirects": True,
            "headers": headers,
        }
        effective_proxy = proxy or self._current_proxy()
        if effective_proxy:
            kwargs["proxy"] = effective_proxy
        return httpx.AsyncClient(**kwargs)

    async def close(self):
        """关闭 HTTP 客户端，释放资源"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── 安全请求封装 ──────────────────────────────────

    async def _safe_get(self, url: str, **kwargs) -> httpx.Response:
        """带重试 + 异常分类 + UA/代理轮换的 GET 请求"""
        async def _do_request():
            # 每次重试都新建 client，便于切换 UA/代理
            client = self._build_client()
            try:
                resp = await client.get(url, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                raise NetworkError(f"网络错误 {url}: {e}") from e
            finally:
                await client.aclose()

            if resp.status_code == 403:
                raise BlockedError(f"被反爬拦截 {url} (403)")
            if resp.status_code == 429:
                raise HTTPStatusError(f"频控 429 {url}", 429)
            if resp.status_code >= 400:
                raise HTTPStatusError(f"HTTP {resp.status_code} {url}", resp.status_code)
            return resp

        return await retry_async(
            _do_request,
            max_retries=self.max_retries,
            retryable_exceptions=(NetworkError, HTTPStatusError, httpx.TimeoutException),
        )

    async def _safe_post(self, url: str, **kwargs) -> httpx.Response:
        """带重试 + 异常分类 + UA/代理轮换的 POST 请求"""
        async def _do_request():
            client = self._build_client()
            try:
                resp = await client.post(url, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                raise NetworkError(f"网络错误 {url}: {e}") from e
            finally:
                await client.aclose()

            if resp.status_code == 403:
                raise BlockedError(f"被反爬拦截 {url} (403)")
            if resp.status_code == 429:
                raise HTTPStatusError(f"频控 429 {url}", 429)
            if resp.status_code >= 400:
                raise HTTPStatusError(f"HTTP {resp.status_code} {url}", resp.status_code)
            return resp

        return await retry_async(
            _do_request,
            max_retries=self.max_retries,
            retryable_exceptions=(NetworkError, HTTPStatusError, httpx.TimeoutException),
        )

    @staticmethod
    def _safe_parse_json(text: str) -> dict:
        """安全解析 JSON，失败抛 ParseError"""
        try:
            import json
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            raise ParseError(f"JSON 解析失败: {e}")

    # ── 延迟与流程 ────────────────────────────────────

    async def _delay(self):
        """请求间延迟"""
        await asyncio.sleep(self.request_delay)

    async def run(self, max_items: int | None = None) -> list[CrawlResult]:
        """执行完整爬取流程

        Args:
            max_items: 限制抓取的详情数量（None 表示不限制，用于测试/限流）
        """
        logger.info(f"[{self.platform_name}] 开始爬取...")

        try:
            detail_urls = await self.fetch_list()
        except CrawlerError as e:
            logger.error(f"[{self.platform_name}] 列表页抓取失败: {e}")
            return []

        logger.info(f"[{self.platform_name}] 获取到 {len(detail_urls)} 个详情页链接")

        if max_items is not None:
            detail_urls = detail_urls[:max_items]
            logger.info(f"[{self.platform_name}] 限流：仅抓取前 {len(detail_urls)} 条")

        results: list[CrawlResult] = []
        for url in detail_urls:
            try:
                result = await self.fetch_detail(url)
                results.append(result)
                await self._delay()
            except BlockedError as e:
                logger.error(f"[{self.platform_name}] 被拦截，停止抓取: {url}, {e}")
                break
            except CrawlerError as e:
                logger.error(f"[{self.platform_name}] 抓取失败: {url}, {e}")
                results.append(CrawlResult(
                    source_platform=self.platform_name,
                    source_url=url,
                    raw_title="",
                    success=False,
                    error_message=str(e),
                ))
            except Exception as e:
                logger.exception(f"[{self.platform_name}] 未预期错误: {url}, {e}")
                results.append(CrawlResult(
                    source_platform=self.platform_name,
                    source_url=url,
                    raw_title="",
                    success=False,
                    error_message=f"未预期错误: {e}",
                ))

        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"[{self.platform_name}] 爬取完成，共 {len(results)} 条 "
            f"(成功 {success_count}, 失败 {len(results) - success_count})"
        )
        return results
