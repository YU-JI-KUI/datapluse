"""
Pipeline 引擎（按 dataset 隔离）
流程：process → pre_annotate → embed → check

每个步骤严格按 dataset_id 隔离，配置从 DB t_system_config 读取（热更新）。
stage 流转使用 t_data_state，不再直接更新 t_data_item 内嵌字段。
pre_annotation 结果写入 t_pre_annotation，冲突写入 t_conflict。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from datapulse.modules.conflict import run_conflict_detection
from datapulse.modules.embedding import embed_text
from datapulse.modules.model import pre_annotate_batch
from datapulse.modules.processing import process_item
from datapulse.modules.vector import rebuild_index
from datapulse.repository.base import get_db
from datapulse.repository.embeddings import get_emb

STEPS = ["process", "pre_annotate", "embed", "check"]
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _set_status(
    dataset_id: int,
    status: str,
    step: str = "",
    progress: int = 0,
    detail: dict[str, Any] | None = None,
    **extra: Any,
) -> None:
    db   = get_db()
    data: dict[str, Any] = {
        "status":       status,
        "current_step": step,
        "progress":     progress,
        "detail":       detail or {},
        "updated_at":   _now(),
        **extra,
    }
    db.set_pipeline_status(dataset_id, data)


def _make_detail(processed: int, total: int, skipped: int, start_time: float) -> dict[str, Any]:
    elapsed = time.time() - start_time
    speed   = processed / elapsed if elapsed > 0 else 0
    eta     = int((total - processed) / speed) if speed > 0 else 0
    pct     = processed / total * 100 if total > 0 else 0
    return {
        "processed":       processed,
        "total":           total,
        "skipped":         skipped,
        "pct":             f"{pct:.1f}%",
        "speed_per_sec":   round(speed, 1),
        "eta_seconds":     eta,
        "elapsed_seconds": round(elapsed, 1),
    }


# ── 单步执行 ──────────────────────────────────────────────────────────────────

# 每处理多少条数据更新一次进度（防止 _set_status 每条都写一次 DB）
_STATUS_UPDATE_INTERVAL = 500


async def step_process(dataset_id: int) -> dict[str, Any]:
    """清洗 raw → cleaned

    优化：
      1. bulk_update_stage 一次 UPDATE 代替 N 次逐行 UPDATE
      2. _set_status 每 _STATUS_UPDATE_INTERVAL 条更新一次，减少 DB 写入
    """
    db         = get_db()
    raw_items  = db.list_data_by_status(dataset_id, "raw")
    total      = len(raw_items)
    if total == 0:
        return {"step": "process", "processed": 0, "skipped": 0}

    start_time   = time.time()
    skipped      = 0
    processed_ids: list[int] = []

    for i, item in enumerate(raw_items):
        updated = process_item(item)
        processed_ids.append(updated.get("id", item["id"]))

        # 每隔 N 条或最后一条才写一次状态（避免 6 万次 DB round-trip）
        if (i + 1) % _STATUS_UPDATE_INTERVAL == 0 or (i + 1) == total:
            _set_status(
                dataset_id, "running", "process",
                int((i + 1) / total * 100),
                detail=_make_detail(i + 1, total, skipped, start_time),
            )

    # 一次 bulk UPDATE 代替 N 次逐行 update_stage
    db.bulk_update_stage(processed_ids, "cleaned", updated_by="pipeline")

    return {"step": "process", "processed": total - skipped, "skipped": skipped}


async def step_pre_annotate(dataset_id: int) -> dict[str, Any]:
    """预标注 cleaned → pre_annotated（结果写入 t_pre_annotation）

    优化：
      1. 每个 batch 的预标注和 stage 更新都批量提交（两次 DB 操作代替 2N 次）
      2. _set_status 按 batch 粒度更新（已经是 batch_size 级别，合理）
    """
    db         = get_db()
    cfg        = db.get_dataset_config(dataset_id)
    items      = db.list_data_by_status(dataset_id, "cleaned")
    total      = len(items)
    if total == 0:
        return {"step": "pre_annotate", "annotated": 0, "skipped": 0}

    batch_size = cfg.get("pipeline", {}).get("batch_size", 32)
    model_name = cfg.get("llm", {}).get("model_name", "mock")
    annotated  = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        batch   = items[i : i + batch_size]
        results = await pre_annotate_batch(batch, cfg)

        # 收集本 batch 的预标注记录和 data_id 列表
        pre_records: list[dict] = []
        batch_ids:   list[int]  = []
        for item, label, score in results:
            data_id = item["id"]
            pre_records.append({
                "data_id":    data_id,
                "model_name": model_name,
                "label":      label,
                "score":      score,
                "created_by": "pipeline",
            })
            batch_ids.append(data_id)
            annotated += 1

        # 批量写预标注（一次 INSERT）
        db.bulk_create_pre_annotations(pre_records)
        # 批量更新 stage（一次 UPDATE）
        db.bulk_update_stage(batch_ids, "pre_annotated", updated_by="pipeline")

        # 每隔一定 batch 数更新一次进度，避免过于频繁
        batches_done = (i // batch_size) + 1
        if batches_done % max(1, _STATUS_UPDATE_INTERVAL // batch_size) == 0 or annotated == total:
            _set_status(
                dataset_id, "running", "pre_annotate",
                int(annotated / total * 100),
                detail=_make_detail(annotated, total, 0, start_time),
            )

    return {"step": "pre_annotate", "annotated": annotated, "skipped": 0}


async def step_embed(dataset_id: int) -> dict[str, Any]:
    """为 pre_annotated / annotated / checked 数据生成 embedding

    优化：_set_status 每 _STATUS_UPDATE_INTERVAL 条更新一次。
    """
    db    = get_db()
    cfg   = db.get_dataset_config(dataset_id)
    items = []
    for stage in ["pre_annotated", "annotated", "checked"]:
        items.extend(db.list_data_by_status(dataset_id, stage))

    total = len(items)
    if total == 0:
        return {"step": "embed", "embedded": 0, "skipped": 0}

    emb        = get_emb()
    embedded   = 0
    skipped    = 0
    start_time = time.time()

    for i, item in enumerate(items):
        if emb.load(item["id"]) is not None:
            skipped  += 1
            embedded += 1
        else:
            vec = embed_text(item["content"], cfg)
            emb.save(item["id"], vec)
            embedded += 1

        if (i + 1) % _STATUS_UPDATE_INTERVAL == 0 or (i + 1) == total:
            _set_status(
                dataset_id, "running", "embed",
                int(embedded / total * 100),
                detail=_make_detail(embedded, total, skipped, start_time),
            )

    count = rebuild_index()
    return {"step": "embed", "embedded": embedded, "skipped": skipped, "index_size": count}


async def step_check(dataset_id: int) -> dict[str, Any]:
    """冲突检测 annotated → checked（干净）或保持 annotated（有冲突）"""
    _set_status(dataset_id, "running", "check", 10, detail={"pct": "10%", "total": 0})
    result = await run_conflict_detection(dataset_id)
    total  = result.get("total", 0)
    _set_status(
        dataset_id, "running", "check", 100,
        detail={
            "total":              total,
            "pct":                "100%",
            "label_conflicts":    result.get("label_conflicts", 0),
            "semantic_conflicts": result.get("semantic_conflicts", 0),
            "clean":              result.get("clean", 0),
        },
    )
    return {"step": "check", **result}


# ── 全量 Pipeline ──────────────────────────────────────────────────────────────


async def run_all(dataset_id: int) -> None:
    _set_status(dataset_id, "running", "process", 0, started_at=_now())
    try:
        r1 = await step_process(dataset_id)
        r2 = await step_pre_annotate(dataset_id)
        r3 = await step_embed(dataset_id)
        r4 = await step_check(dataset_id)
        _set_status(dataset_id, "completed", "", 100,
                    finished_at=_now(), results=[r1, r2, r3, r4])
    except Exception as e:
        _set_status(dataset_id, "error", "", 0, error=str(e), finished_at=_now())
        raise


def run_all_sync(dataset_id: int) -> None:
    """同步包装器，供 FastAPI BackgroundTasks 使用。

    BackgroundTasks 对 sync 函数会自动放到线程池（run_in_threadpool）执行，
    不会阻塞主 asyncio 事件循环。内部通过 asyncio.run() 创建独立事件循环，
    以支持 step_pre_annotate 中的 async LLM 调用。
    """
    import asyncio as _asyncio
    _asyncio.run(run_all(dataset_id))


async def run_step(dataset_id: int, step: str) -> dict[str, Any]:
    if step not in STEPS:
        raise ValueError(f"未知步骤: {step}，可选: {STEPS}")

    _set_status(dataset_id, "running", step, 0, started_at=_now())
    try:
        fn = {
            "process":      step_process,
            "pre_annotate": step_pre_annotate,
            "embed":        step_embed,
            "check":        step_check,
        }[step]
        result = await fn(dataset_id)
        _set_status(dataset_id, "completed", step, 100,
                    finished_at=_now(), results=result)
        return result
    except Exception as e:
        _set_status(dataset_id, "error", step, 0, error=str(e), finished_at=_now())
        raise
