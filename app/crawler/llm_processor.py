"""
LLM 数据处理器 — 对应架构图中的「AI 数据清洗节点 (D2)」
将爬虫抓取的非结构化文本转化为标准化数据库字段

⚠️ Mock 实现 — 不调用真实 LLM API
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

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
    llm_confidence: float = 0.0
    raw_data: dict = field(default_factory=dict)


class LLMProcessor:
    """
    LLM 数据清洗节点

    职责：
    1. 接收爬虫原始数据 (CrawlResult)
    2. 调用 LLM API (GPT-4 / Claude) 进行信息抽取
    3. 将非结构化文本转化为 StandardizedHackathon
    4. 计算置信度并标记低质量数据供人工审核

    Mock 实现：返回模拟的标准化数据
    """

    # LLM Prompt 模板（供后续真实实现参考）
    EXTRACTION_PROMPT = """
    你是一个黑客松信息提取专家。请从以下文本中提取结构化字段：

    原始文本：
    {raw_text}

    请提取以下字段（如果找不到则填 null）：
    - name: 活动名称
    - summary: 一句话摘要（50字以内）
    - registration_start: 报名开始日期 (YYYY-MM-DD)
    - registration_end: 报名截止日期 (YYYY-MM-DD)
    - event_start: 活动开始日期 (YYYY-MM-DD)
    - event_end: 活动结束日期 (YYYY-MM-DD)
    - mode: online / offline / hybrid
    - track_tags: 赛道标签数组
    - tech_tags: 技术栈标签数组
    - prize_pool: 奖金池（原文格式）
    - prize_pool_usd: 奖金池（USD 数值，估算）
    - location: 详细地点
    - country: 国家
    - city: 城市
    - organizer: 主办方

    请以 JSON 格式返回结果，并附加一个 confidence 字段（0.0-1.0，表示提取质量置信度）。
    """

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    async def process(self, crawl_result: CrawlResult) -> StandardizedHackathon:
        """
        处理单条爬取结果

        Mock 实现：提取 CrawlResult 中的 raw_title，生成标准化数据
        生产环境：调用 LLM API，传入 EXTRACTION_PROMPT
        """
        logger.info(f"[LLM] 处理: {crawl_result.raw_title} (来源: {crawl_result.source_platform})")

        # Mock: 基于原始数据假装做了提取
        name = crawl_result.raw_data.get("title") or crawl_result.raw_title
        slug = name.lower().replace(" ", "-").replace("/", "-")

        return StandardizedHackathon(
            name=name,
            slug=slug,
            description=crawl_result.raw_description,
            summary=f"Mock 摘要: {name}",
            event_start="2026-07-01",
            event_end="2026-07-03",
            status="upcoming",
            mode="online",
            track_tags=crawl_result.raw_data.get("tags", []),
            tech_tags=[],
            prize_pool=crawl_result.raw_data.get("prize"),
            source_url=crawl_result.source_url,
            source_platform=crawl_result.source_platform,
            llm_confidence=0.85,
            raw_data=crawl_result.raw_data,
        )

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