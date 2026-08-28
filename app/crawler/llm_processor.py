"""
LLM 数据处理器 — 调用阶跃星辰 Step API 进行结构化信息提取
对应架构图中的「AI 数据清洗节点 (D2)」
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.config import settings
from app.crawler.base import CrawlResult

logger = logging.getLogger(__name__)


@dataclass
class StandardizedHackathon:
    """经 LLM 清洗后的标准化黑客松数据"""
    name: str
    slug: str
    description: str | None = None
    summary: str | None = None
    registration_start: str | None = None
    registration_end: str | None = None
    event_start: str | None = None
    event_end: str | None = None
    status: str = "upcoming"
    mode: str = "online"
    track_tags: list[str] = field(default_factory=list)
    tech_tags: list[str] = field(default_factory=list)
    prize_pool: str | None = None
    prize_pool_usd: float | None = None
    location: str | None = None
    country: str | None = None
    city: str | None = None
    source_url: str = ""
    source_platform: str = ""
    organizer: str | None = None
    sponsors: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    rules: str | None = None
    llm_confidence: float = 0.0
    raw_data: dict = field(default_factory=dict)
    cover_image: str | None = None  # ← 新增：封面图 URL
    image_urls: list[str] = field(default_factory=list)  # ← 新增：所有相关图片 URL


EXTRACTION_PROMPT = """你是一个黑客松信息提取专家。请从以下原始数据中提取结构化字段。

原始数据：
{raw_text}

请提取以下字段，以JSON格式返回：
{{
    "name": "活动名称",
    "summary": "一句话摘要（50字以内）",
    "registration_start": "报名开始日期 (YYYY-MM-DD，无法确定填null)",
    "registration_end": "报名截止日期 (YYYY-MM-DD，无法确定填null)",
    "event_start": "活动开始日期 (YYYY-MM-DD，无法确定填null)",
    "event_end": "活动结束日期 (YYYY-MM-DD，无法确定填null)",
    "mode": "online/offline/hybrid",
    "track_tags": ["赛道标签数组"],
    "tech_tags": ["技术栈标签数组"],
    "prize_pool": "奖金池（原文格式）",
    "prize_pool_usd": "奖金USD数值（估算，无法确定填null）",
    "location": "详细地点",
    "country": "国家",
    "city": "城市",
    "organizer": "主办方",
    "sponsors": ["赞助商数组"],
    "requirements": ["参赛条件数组"],
    "timeline": [{{"phase": "阶段名", "date": "日期"}}],
    "rules": "比赛规则摘要(200字以内)",
    "cover_image": "封面图/海报图片URL（无法确定填null）",
    "image_urls": ["所有相关图片URL数组（海报、奖品图、场地图等）"],
    "confidence": 0.85
}}

注意：只返回JSON，不要其他内容。无法确定的字段填null。"""


class _ResultCache:
    """简单的内存缓存（带 TTL），避免对相同 raw_data 重复调用 LLM"""

    def __init__(self, ttl: int = 86400):
        self.ttl = ttl
        self._store: dict[str, tuple[float, dict]] = {}

    def _key(self, raw_text: str) -> str:
        return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    def get(self, raw_text: str) -> dict | None:
        key = self._key(raw_text)
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, raw_text: str, value: dict):
        self._store[self._key(raw_text)] = (time.time(), value)

    def clear(self):
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


def _extract_json_from_text(content: str) -> dict | None:
    """从 LLM 返回的文本中健壮地提取 JSON

    支持以下格式：
    - 纯 JSON
    - ```json ... ``` 代码块
    - ``` ... ``` 代码块
    - 文本中嵌入的 JSON 对象（取第一个完整 {}）
    """
    if not content:
        return None

    text = content.strip()

    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. 尝试 ```json ... ``` 代码块
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. 尝试 ``` ... ``` 代码块
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # 4. 尝试从文本中提取第一个完整 JSON 对象（平衡花括号）
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except (json.JSONDecodeError, ValueError):
                    # 继续找下一个 }
                    continue
    return None


class LLMProcessor:
    """LLM 数据清洗节点 — 调用阶跃星辰 Step API

    特性：
    - 结果缓存（避免对相同 raw_data 重复调用）
    - 健壮 JSON 解析（支持代码块、嵌入 JSON、平衡花括号提取）
    - 降级策略（LLM 失败时返回预填充的基础结果）
    - 批量处理（带并发限制 + 速率限制）
    - 成本控制（token 估算、调用计数、熔断）
    """

    # 熔断阈值
    MAX_CONSECUTIVE_FAILURES = 5
    # 速率限制：每秒最大请求数
    MAX_REQUESTS_PER_SECOND = 2.0

    def __init__(self, cache_ttl: int | None = None):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_API_BASE_URL
        self.model = settings.LLM_MODEL
        self.cache = _ResultCache(cache_ttl or settings.CRAWLER_LLM_CACHE_TTL)
        # 成本与统计
        self._total_calls = 0
        self._total_cache_hits = 0
        self._total_failures = 0
        self._consecutive_failures = 0
        self._circuit_open = False
        # 速率限制：记录最近请求时间戳
        self._last_request_time = 0.0
        self._min_interval = 1.0 / self.MAX_REQUESTS_PER_SECOND

    async def process(self, crawl_result: CrawlResult) -> StandardizedHackathon:
        """处理单条爬取结果：调用 LLM API 提取结构化数据"""
        logger.info(f"[LLM] 处理: {crawl_result.raw_title} (来源: {crawl_result.source_platform})")

        # 先从 raw_data 中提取已知字段
        raw = crawl_result.raw_data
        name = raw.get("title") or raw.get("name") or crawl_result.raw_title or "未命名活动"
        slug = self._make_slug(name)

        # 构建基础结果（即使 LLM 失败也能返回）
        base = StandardizedHackathon(
            name=name,
            slug=slug,
            description=crawl_result.raw_description,
            source_url=crawl_result.source_url,
            source_platform=crawl_result.source_platform,
            raw_data=raw,
        )

        # 从 raw_data 预填充已知字段
        base.event_start = raw.get("start_date") or raw.get("event_start")
        base.event_end = raw.get("end_date") or raw.get("event_end")
        base.registration_end = raw.get("signup_end") or raw.get("registration_end")
        base.prize_pool = raw.get("prize") or raw.get("prize_pool")
        base.organizer = raw.get("organizer")
        base.location = raw.get("location")
        base.mode = raw.get("mode", "online")
        base.track_tags = raw.get("tracks", []) or []
        base.sponsors = raw.get("sponsors", []) or []

        # 调用 LLM 补充提取
        if not all((self.api_key, self.base_url, self.model)):
            logger.warning("[LLM] API Key、Base URL 或模型未配置，跳过 LLM 清洗")
            return base

        try:
            llm_result = await self._call_llm(raw)
            if llm_result:
                self._merge_llm_result(base, llm_result, name)
            else:
                logger.warning(f"[LLM] 无法从响应中提取 JSON: {crawl_result.raw_title}")
        except httpx.HTTPStatusError as e:
            logger.error(f"[LLM] API HTTP 错误: {e.response.status_code}")
        except httpx.TimeoutException:
            logger.error("[LLM] API 超时")
        except Exception as e:
            logger.error(f"[LLM] API 调用失败: {e}")

        return base

    def _merge_llm_result(self, base: StandardizedHackathon, llm_result: dict, original_name: str):
        """将 LLM 结果合并到 base（LLM 结果覆盖/补充空字段）"""
        for key in ["summary", "registration_start", "registration_end",
                    "event_start", "event_end", "mode", "prize_pool",
                    "prize_pool_usd", "location", "country", "city",
                    "organizer", "rules", "cover_image"]:
            val = llm_result.get(key)
            # summary、rules、cover_image 总是覆盖（LLM 生成/提取质量更高）
            # 其他字段仅在 base 为空时补充
            if val is None:
                continue
            if key in ("summary", "rules", "cover_image"):
                setattr(base, key, val)
            elif not getattr(base, key, None):
                setattr(base, key, val)

        if llm_result.get("track_tags"):
            base.track_tags = list(dict.fromkeys(base.track_tags + llm_result["track_tags"]))
        if llm_result.get("tech_tags"):
            base.tech_tags = llm_result["tech_tags"]
        if llm_result.get("sponsors"):
            base.sponsors = list(dict.fromkeys(base.sponsors + llm_result["sponsors"]))
        if llm_result.get("requirements"):
            base.requirements = llm_result["requirements"]
        if llm_result.get("timeline"):
            base.timeline = llm_result["timeline"]
        if llm_result.get("image_urls"):
            base.image_urls = list(dict.fromkeys(base.image_urls + llm_result["image_urls"]))
        if llm_result.get("name") and llm_result["name"] != original_name:
            base.name = llm_result["name"]
            base.slug = self._make_slug(base.name)

        base.llm_confidence = float(llm_result.get("confidence", 0.7) or 0.7)

    @staticmethod
    def _make_slug(name: str) -> str:
        """生成 URL-safe slug"""
        slug = name.lower().replace(" ", "-").replace("/", "-")
        # 移除非字母数字字符（保留中文）
        slug = re.sub(r"[^\w\u4e00-\u9fff\-]", "", slug, flags=re.UNICODE)
        return slug[:500] or "untitled"

    async def _call_llm(self, raw_data: dict) -> dict | None:
        """调用阶跃星辰 API（带缓存 + 熔断 + 速率限制）

        熔断策略：
        - 网络错误 / HTTP 错误 / 超时 → 计入 consecutive_failures，触发熔断
        - JSON 解析失败 → 计入 parse_failures，不触发熔断（LLM 偶尔返回格式错误是正常的）
        """
        raw_text = json.dumps(raw_data, ensure_ascii=False, default=str)
        if len(raw_text) > 4000:
            raw_text = raw_text[:4000] + "...(truncated)"

        # 缓存命中
        cached = self.cache.get(raw_text)
        if cached is not None:
            self._total_cache_hits += 1
            logger.debug("[LLM] 缓存命中")
            return cached

        # 熔断检查
        if self._circuit_open:
            logger.warning("[LLM] 熔断器开启，跳过调用")
            return None

        # 速率限制
        await self._enforce_rate_limit()

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": EXTRACTION_PROMPT.format(raw_text=raw_text)}
                        ],
                        "temperature": 0.1,
                    },
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]

            # 健壮 JSON 解析
            result = _extract_json_from_text(content)
            if result is not None:
                self.cache.set(raw_text, result)
                self._total_calls += 1
                self._consecutive_failures = 0  # 成功，重置计数
                return result
            # JSON 解析失败：不计入熔断（LLM 偶尔返回格式错误是正常的）
            self._total_failures += 1
            logger.warning(f"[LLM] JSON 解析失败（不计入熔断），原始内容前 200 字: {content[:200]}")
            return None
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.NetworkError) as e:
            # 网络/HTTP 错误：计入熔断
            self._total_failures += 1
            self._consecutive_failures += 1
            self._check_circuit()
            raise
        except Exception as e:
            # 其他未预期错误：计入熔断
            self._total_failures += 1
            self._consecutive_failures += 1
            self._check_circuit()
            raise

    async def _enforce_rate_limit(self):
        """速率限制：确保两次请求间隔不小于 _min_interval"""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _check_circuit(self):
        """熔断检查：连续失败超过阈值时开启熔断"""
        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self._circuit_open = True
            logger.error(
                f"[LLM] 熔断器开启：连续失败 {self._consecutive_failures} 次"
            )

    def reset_circuit(self):
        """手动重置熔断器"""
        self._circuit_open = False
        self._consecutive_failures = 0
        logger.info("[LLM] 熔断器已重置")

    def get_stats(self) -> dict:
        """获取 LLM 调用统计"""
        return {
            "total_calls": self._total_calls,
            "cache_hits": self._total_cache_hits,
            "total_failures": self._total_failures,
            "consecutive_failures": self._consecutive_failures,
            "circuit_open": self._circuit_open,
            "cache_size": len(self.cache),
            "model": self.model,
        }

    async def process_batch(
        self,
        crawl_results: list[CrawlResult],
        concurrency: int = 3,
    ) -> list[StandardizedHackathon]:
        """批量处理爬取结果（带并发限制）

        Args:
            crawl_results: 爬取结果列表
            concurrency: 并发数（避免压垮 LLM API）
        """
        import asyncio

        semaphore = asyncio.Semaphore(concurrency)
        results: list[StandardizedHackathon] = []

        async def _process_one(result: CrawlResult) -> StandardizedHackathon | None:
            async with semaphore:
                try:
                    return await self.process(result)
                except Exception as e:
                    logger.error(f"[LLM] 处理失败: {result.raw_title}, 错误: {e}")
                    return None

        tasks = [_process_one(r) for r in crawl_results]
        completed = await asyncio.gather(*tasks)
        for item in completed:
            if item is not None:
                results.append(item)

        logger.info(f"[LLM] 批量处理完成: {len(results)}/{len(crawl_results)} 条成功")
        return results


# 全局实例
llm_processor = LLMProcessor()
