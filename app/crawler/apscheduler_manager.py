"""
APScheduler 定时任务管理 — 驱动爬虫调度器按计划运行

对应 main.py lifespan 中的 TODO：
    # TODO: 启动 APScheduler 定时爬虫任务

调度策略（对应 CRAWL_SCHEDULE）：
    - dorahacks:    每日 03:00
    - competehub:   每日 04:00
    - devpost:      每日 02:00
    - mlh:          每日 02:30
    - eventbrite:   每6小时
    - saikr:        每日 04:30
    - tianchi:      每日 05:00
    - huodongxing:  每6小时
"""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.crawler.scheduler import scheduler as crawler_scheduler, CRAWL_SCHEDULE

logger = logging.getLogger(__name__)


# 调度配置：平台 → (触发器类型, 参数)
SCHEDULE_JOBS = {
    "devpost":      ("cron", {"hour": 2, "minute": 0}),
    "mlh":          ("cron", {"hour": 2, "minute": 30}),
    "dorahacks":    ("cron", {"hour": 3, "minute": 0}),
    "competehub":   ("cron", {"hour": 4, "minute": 0}),
    "saikr":        ("cron", {"hour": 4, "minute": 30}),
    "tianchi":      ("cron", {"hour": 5, "minute": 0}),
    "ethglobal":    ("cron", {"hour": 5, "minute": 30}),
    "hackathon_com":("cron", {"hour": 6, "minute": 0}),
    "itch_jams":    ("cron", {"hour": 6, "minute": 30}),
    "eventbrite":   ("interval", {"hours": 6}),
    "huodongxing":  ("interval", {"hours": 6}),
}


class SchedulerManager:
    """管理 APScheduler 实例与爬虫任务的绑定"""

    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None
        self._started = False

    @property
    def scheduler(self) -> AsyncIOScheduler | None:
        return self._scheduler

    @property
    def is_running(self) -> bool:
        return self._started and self._scheduler is not None and self._scheduler.running

    def start(self):
        """启动调度器，注册所有定时任务"""
        if self._started:
            logger.warning("[SchedulerManager] 已启动，跳过")
            return

        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

        # 为每个平台注册定时任务
        for platform, (trigger_type, params) in SCHEDULE_JOBS.items():
            job_id = f"crawl_{platform}"
            try:
                if trigger_type == "cron":
                    trigger = CronTrigger(**params)
                else:
                    trigger = IntervalTrigger(**params)

                self._scheduler.add_job(
                    self._run_platform_safe,
                    trigger=trigger,
                    args=[platform],
                    id=job_id,
                    name=f"爬取 {platform}",
                    max_instances=1,           # 同一平台不并发
                    coalesce=True,             # 错过多次只执行一次
                    misfire_grace_time=3600,   # 允许1小时内的迟到执行
                )
                logger.info(f"[SchedulerManager] 注册任务 {job_id}: {CRAWL_SCHEDULE.get(platform, '?')}")
            except Exception as e:
                logger.error(f"[SchedulerManager] 注册 {platform} 失败: {e}")

        # 每日全量去重任务（凌晨6点，在所有平台爬取后）
        self._scheduler.add_job(
            self._run_all_with_dedup_safe,
            trigger=CronTrigger(hour=6, minute=0),
            id="crawl_all_dedup",
            name="全量爬取+去重",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        logger.info("[SchedulerManager] 注册全量去重任务: 每日 06:00")

        self._scheduler.start()
        self._started = True
        logger.info(f"[SchedulerManager] 启动完成，共 {len(self._scheduler.get_jobs())} 个任务")

    async def _run_platform_safe(self, platform: str):
        """安全执行单平台爬取（捕获所有异常，避免任务崩溃）"""
        logger.info(f"[SchedulerManager] 定时任务触发: {platform} @ {datetime.now()}")
        try:
            result = await crawler_scheduler.run_platform(platform, save_json=True)
            logger.info(f"[SchedulerManager] {platform} 完成: {result.get('status')} "
                        f"(raw={result.get('raw_count', 0)}, cleaned={result.get('cleaned_count', 0)})")
            return result
        except Exception as e:
            logger.exception(f"[SchedulerManager] {platform} 任务异常: {e}")
            return {"platform": platform, "status": "error", "error": str(e)}

    async def _run_all_with_dedup_safe(self):
        """安全执行全量爬取+去重"""
        logger.info(f"[SchedulerManager] 全量去重任务触发 @ {datetime.now()}")
        try:
            result = await crawler_scheduler.run_all_with_dedup(save_json=True)
            logger.info(f"[SchedulerManager] 全量去重完成: {result.get('dedup', {})}")
            return result
        except Exception as e:
            logger.exception(f"[SchedulerManager] 全量去重任务异常: {e}")
            return {"status": "error", "error": str(e)}

    def stop(self):
        """停止调度器"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("[SchedulerManager] 已停止")
        self._started = False

    def get_jobs(self) -> list[dict]:
        """获取所有任务状态"""
        if not self._scheduler:
            return []
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs

    def trigger_now(self, platform: str) -> bool:
        """手动触发某平台任务（立即执行）"""
        if not self._scheduler:
            return False
        job_id = f"crawl_{platform}"
        job = self._scheduler.get_job(job_id)
        if job is None:
            logger.warning(f"[SchedulerManager] 任务 {job_id} 不存在")
            return False
        # 修改 next_run_time 为现在
        self._scheduler.modify_job(job_id, next_run_time=datetime.now())
        logger.info(f"[SchedulerManager] 手动触发 {job_id}")
        return True


# 全局实例
scheduler_manager = SchedulerManager()
