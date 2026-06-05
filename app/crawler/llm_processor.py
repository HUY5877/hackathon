"""
LLM 数据处理器 — 调用阶跃星辰 Step API 进行结构化信息提取
对应架构图中的「AI 数据清洗节点 (D2)」
"""

import json
import logging
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
    "prize_pool_usd": 奖金USD数值（估算，无法确定填null）,
    "location": "详细地点",
    "country": "国家",
    "city": "城市",
    "organizer": "主办方",
    "sponsors": ["赞助商数组"],
    "requirements": ["参赛条件数组"],
    "timeline": [{{"phase": "阶段名", "date": "日期"}}],
    "rules": "比赛规则摘要(200字以内)",
    "confidence": 0.85
}}

注意：只返回JSON，不要其他内容。无法确定的字段填null。"""


class LLMProcessor:
    """LLM 数据清洗节点 — 调用阶跃星辰 Step API"""

    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_API_BASE_URL
        self.model = settings.LLM_MODEL

    async def process(self, crawl_result: CrawlResult) -> StandardizedHackathon:
        """处理单条爬取结果：调用 LLM API 提取结构化数据"""
        logger.info(f"[LLM] 处理: {crawl_result.raw_title} (来源: {crawl_result.source_platform})")

        # 先从 raw_data 中提取已知字段
        raw = crawl_result.raw_data
        name = raw.get("title") or raw.get("name") or crawl_result.raw_title
        slug = name.lower().replace(" ", "-").replace("/", "-")[:500]

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
        base.track_tags = raw.get("tracks", [])
        base.sponsors = raw.get("sponsors", [])

        # 调用 LLM 补充提取
        if not self.api_key:
            logger.warning("[LLM] 未配置 API Key，跳过 LLM 清洗")
            return base

        try:
            llm_result = await self._call_llm(raw)
            if llm_result:
                # LLM 结果覆盖/补充空字段
                for key in ["summary", "registration_start", "registration_end",
                            "event_start", "event_end", "mode", "prize_pool",
                            "prize_pool_usd", "location", "country", "city",
                            "organizer", "rules"]:
                    val = llm_result.get(key)
                    if val is not None and (not getattr(base, key, None) or key in ["summary", "rules"]):
                        setattr(base, key, val)

                if llm_result.get("track_tags"):
                    base.track_tags = list(set(base.track_tags + llm_result["track_tags"]))
                if llm_result.get("tech_tags"):
                    base.tech_tags = llm_result["tech_tags"]
                if llm_result.get("sponsors"):
                    base.sponsors = list(set(base.sponsors + llm_result["sponsors"]))
                if llm_result.get("requirements"):
                    base.requirements = llm_result["requirements"]
                if llm_result.get("timeline"):
                    base.timeline = llm_result["timeline"]
                if llm_result.get("name") and llm_result["name"] != name:
                    base.name = llm_result["name"]

                base.llm_confidence = llm_result.get("confidence", 0.7)

        except Exception as e:
            logger.error(f"[LLM] API 调用失败: {e}")

        return base

    async def _call_llm(self, raw_data: dict) -> dict | None:
        """调用阶跃星辰 API"""
        raw_text = json.dumps(raw_data, ensure_ascii=False, default=str)
        if len(raw_text) > 4000:
            raw_text = raw_text[:4000] + "...(truncated)"

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

        # 提取 JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return json.loads(content.strip())

    async def process_batch(self, crawl_results: list[CrawlResult]) -> list[StandardizedHackathon]:
        """批量处理爬取结果"""
        results = []
        for result in crawl_results:
            try:
                standardized = await self.process(result)
                results.append(standardized)
            except Exception as e:
                logger.error(f"[LLM] 处理失败: {result.raw_title}, 错误: {e}")
        logger.info(f"[LLM] 批量处理完成: {len(results)}/{len(crawl_results)} 条成功")
        return results


# 全局实例
llm_processor = LLMProcessor()
