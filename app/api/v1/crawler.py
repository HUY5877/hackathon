"""爬虫管理 API — 暴露爬虫触发、状态查询、历史记录能力

对应架构图中的「自动化爬虫引擎 (D1)」控制面接口。

端点：
    GET  /api/v1/crawler/status          — 爬虫系统状态
    GET  /api/v1/crawler/jobs             — 定时任务列表
    GET  /api/v1/crawler/history          — 运行历史
    GET  /api/v1/crawler/stats            — LLM 调用统计
    POST /api/v1/crawler/run/{platform}   — 触发单平台爬取
    POST /api/v1/crawler/run-all          — 触发全量爬取（含去重）
    POST /api/v1/crawler/trigger/{platform} — 触发定时任务立即执行
    POST /api/v1/crawler/circuit/reset    — 重置 LLM 熔断器
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.crawler.scheduler import scheduler, CRAWLER_REGISTRY, CRAWL_SCHEDULE
from app.crawler.apscheduler_manager import scheduler_manager
from app.crawler.llm_processor import llm_processor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crawler", tags=["爬虫管理"])


# ── 响应模型 ──────────────────────────────────────────

class CrawlerStatusResponse(BaseModel):
    platforms: list[str]
    schedules: dict[str, str]
    llm_model: str
    status: str
    stats: dict
    recent_runs: list[dict]
    output_dir: str


class RunResultResponse(BaseModel):
    platform: str
    status: str
    raw_count: int = 0
    cleaned_count: int = 0
    elapsed_seconds: float = 0.0
    error: str | None = None


class TriggerResponse(BaseModel):
    job_id: str
    triggered: bool
    message: str


# ── 端点 ──────────────────────────────────────────────

@router.get("/status", response_model=CrawlerStatusResponse)
async def get_crawler_status():
    """获取爬虫系统状态（公开端点，不含敏感信息）"""
    status = scheduler.get_status()
    return CrawlerStatusResponse(**status)


@router.get("/jobs")
async def get_jobs():
    """获取所有定时任务列表"""
    if not scheduler_manager.is_running:
        return {"jobs": [], "running": False}
    return {"jobs": scheduler_manager.get_jobs(), "running": True}


@router.get("/history")
async def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(get_current_user),
):
    """获取运行历史（需认证）"""
    return {"history": scheduler.get_history(limit=limit)}


@router.get("/stats")
async def get_llm_stats(_: dict = Depends(get_current_user)):
    """获取 LLM 调用统计（需认证）"""
    return llm_processor.get_stats()


@router.post("/run/{platform}", response_model=RunResultResponse)
async def run_platform(
    platform: str,
    save_json: bool = Query(default=True),
    _: dict = Depends(get_current_user),
):
    """触发单平台爬取（需认证）

    - platform: 平台名，如 devpost / mlh / tianchi / dorahacks 等
    - save_json: 是否保存结果到 JSON 文件
    """
    if platform not in CRAWLER_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"未知平台: {platform}，可用平台: {list(CRAWLER_REGISTRY.keys())}"
        )

    logger.info(f"[API] 用户触发爬取: {platform}")
    result = await scheduler.run_platform(platform, save_json=save_json)
    return RunResultResponse(**result)


@router.post("/run-all")
async def run_all(
    save_json: bool = Query(default=True),
    _: dict = Depends(get_current_user),
):
    """触发全量爬取 + 跨平台去重（需认证）

    这是完整的爬取流水线：爬取 → LLM 清洗 → 去重 → 保存
    """
    logger.info("[API] 用户触发全量爬取")
    result = await scheduler.run_all_with_dedup(save_json=save_json)
    return result


@router.post("/trigger/{platform}", response_model=TriggerResponse)
async def trigger_scheduled_job(
    platform: str,
    _: dict = Depends(get_current_user),
):
    """触发定时任务立即执行（不等待，异步执行）（需认证）"""
    if platform not in CRAWLER_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"未知平台: {platform}"
        )

    job_id = f"crawl_{platform}"
    triggered = scheduler_manager.trigger_now(platform)
    return TriggerResponse(
        job_id=job_id,
        triggered=triggered,
        message=f"已触发 {platform} 定时任务" if triggered else f"触发失败，任务 {job_id} 不存在或调度器未运行",
    )


@router.post("/circuit/reset")
async def reset_circuit(_: dict = Depends(get_current_user)):
    """重置 LLM 熔断器（需认证）"""
    llm_processor.reset_circuit()
    return {"status": "ok", "message": "熔断器已重置"}
