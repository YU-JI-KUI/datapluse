"""
定时任务调度器

使用 APScheduler AsyncIOScheduler，集成到 FastAPI lifespan。
所有定时任务运行在 asyncio 事件循环中，与主服务共享进程，无需额外进程/队列。

当前任务
--------
embed_all_datasets  -- 每天上海时间 02:00 对所有活跃数据集触发向量化（embedding + FAISS）
"""

from __future__ import annotations

import asyncio
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_log = _log = structlog.get_logger(__name__)

_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 全局调度器实例（在 startup 启动，在 shutdown 停止）
_scheduler: AsyncIOScheduler | None = None


async def _embed_all_datasets() -> None:
    """遍历所有活跃数据集，依次触发向量化。

    每个数据集串行执行：避免并发 embedding 推理把 GPU/CPU 打满。
    失败时记录日志并继续下一个，不影响其他数据集。
    """
    from datapulse.pipeline.engine import run_embed_job
    from datapulse.repository.base import get_db

    db = get_db()
    try:
        result = db.list_datasets(status="active")
        # list_datasets 返回分页结构或列表，兼容两种格式
        datasets: list[dict] = result.get("list", result) if isinstance(result, dict) else result
    except Exception:
        _log.exception("scheduler.embed_all: failed to list datasets")
        return

    _log.info("scheduler.embed_all started", dataset_count=len(datasets))

    for ds in datasets:
        dataset_id: int = ds.get("id")
        if not dataset_id:
            continue
        try:
            _log.info("scheduler.embed_all: embedding dataset", dataset_id=dataset_id)
            await run_embed_job(dataset_id, operator="scheduler")
            _log.info("scheduler.embed_all: done", dataset_id=dataset_id)
        except Exception:
            _log.exception("scheduler.embed_all: error embedding dataset", dataset_id=dataset_id)
            # 继续下一个数据集

    _log.info("scheduler.embed_all finished", dataset_count=len(datasets))


def start_scheduler() -> AsyncIOScheduler:
    """创建并启动调度器，注册所有定时任务。在 FastAPI lifespan startup 调用。"""
    global _scheduler

    scheduler = AsyncIOScheduler()

    # 每天上海时间 02:00 触发全量向量化
    scheduler.add_job(
        _embed_all_datasets,
        trigger=CronTrigger(hour=2, minute=0, timezone=_SHANGHAI),
        id="embed_all_datasets",
        name="Daily embedding for all active datasets",
        replace_existing=True,
        misfire_grace_time=600,   # 允许最多 10 分钟延迟触发（服务重启恢复场景）
    )

    scheduler.start()
    _scheduler = scheduler

    next_run = scheduler.get_job("embed_all_datasets").next_run_time
    _log.info("scheduler started", next_embed_run=str(next_run))
    return scheduler


def stop_scheduler() -> None:
    """关闭调度器。在 FastAPI lifespan shutdown 调用。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _log.info("scheduler stopped")
    _scheduler = None
