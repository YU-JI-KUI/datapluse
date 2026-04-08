"""
Pipeline 引擎（按 dataset 隔离）
流程：process → pre_annotate → embed → check

每个步骤都接受 dataset_id 参数，操作范围严格限制在该 dataset 内。
配置从 DB system_config 表读取，支持热更新。
进度详情：数量 / 百分比 / 速度 / ETA
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from modules.conflict import run_conflict_detection
from modules.embedding import embed_text
from modules.model import pre_annotate_batch
from modules.processing import process_item
from modules.vector import get_index, rebuild_index
from storage.db import get_db
from storage.embeddings import get_emb

STEPS = ["process", "pre_annotate", "embed", "check"]

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _set_status(
    dataset_id: str,
    status: str,
    step: str = "",
    progress: int = 0,
    detail: dict[str, Any] | None = None,
    **extra,
) -> None:
    db = get_db()
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
        "processed":      processed,
        "total":          total,
        "skipped":        skipped,
        "pct":            f"{pct:.1f}%",
        "speed_per_sec":  round(speed, 1),
        "eta_seconds":    eta,
        "elapsed_seconds": round(elapsed, 1),
    }


# ── 单步执行 ──────────────────────────────────────────────────────────────────

async def step_process(dataset_id: str) -> dict[str, Any]:
    """清洗 raw → processed"""
    db = get_db()
    raw_items = db.list_by_status(dataset_id, "raw")
    total = len(raw_items)
    if total == 0:
        return {"step": "process", "processed": 0, "skipped": 0}

    start_time = time.time()
    skipped = 0
    for i, item in enumerate(raw_items):
        updated = process_item(item)
        if not updated:
            skipped += 1
            continue
        db.update(updated)
        _set_status(dataset_id, "running", "process", int((i + 1) / total * 100),
                    detail=_make_detail(i + 1, total, skipped, start_time))

    return {"step": "process", "processed": total - skipped, "skipped": skipped}


async def step_pre_annotate(dataset_id: str) -> dict[str, Any]:
    """预标注 processed → pre_annotated"""
    db  = get_db()
    cfg = db.get_dataset_config(dataset_id)
    items = db.list_by_status(dataset_id, "processed")
    total = len(items)
    if total == 0:
        return {"step": "pre_annotate", "annotated": 0, "skipped": 0}

    batch_size = cfg.get("pipeline", {}).get("batch_size", 32)
    annotated  = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        batch   = items[i: i + batch_size]
        results = await pre_annotate_batch(batch, cfg)
        for r in results:
            db.update(r)
        annotated += len(results)
        _set_status(dataset_id, "running", "pre_annotate", int(annotated / total * 100),
                    detail=_make_detail(annotated, total, 0, start_time))

    return {"step": "pre_annotate", "annotated": annotated, "skipped": 0}


async def step_embed(dataset_id: str) -> dict[str, Any]:
    """为 pre_annotated / labeled / checked 数据生成 embedding"""
    db  = get_db()
    cfg = db.get_dataset_config(dataset_id)
    items = []
    for s in ["pre_annotated", "labeled", "checked"]:
        items.extend(db.list_by_status(dataset_id, s))

    total = len(items)
    if total == 0:
        return {"step": "embed", "embedded": 0, "skipped": 0}

    emb        = get_emb()
    embedded   = 0
    skipped    = 0
    start_time = time.time()

    for item in items:
        if emb.load(item["id"]) is not None:
            skipped += 1
            embedded += 1
        else:
            vec = embed_text(item["text"], cfg)
            emb.save(item["id"], vec)
            embedded += 1
        _set_status(dataset_id, "running", "embed", int(embedded / total * 100),
                    detail=_make_detail(embedded, total, skipped, start_time))

    count = rebuild_index()
    return {"step": "embed", "embedded": embedded, "skipped": skipped, "index_size": count}


async def step_check(dataset_id: str) -> dict[str, Any]:
    """冲突检测 labeled → checked"""
    _set_status(dataset_id, "running", "check", 10, detail={"pct": "10%", "total": 0})
    result = await run_conflict_detection(dataset_id)
    total  = result.get("total", 0)
    _set_status(dataset_id, "running", "check", 100, detail={
        "total":              total,
        "pct":                "100%",
        "label_conflicts":    result.get("label_conflicts", 0),
        "semantic_conflicts": result.get("semantic_conflicts", 0),
        "clean":              result.get("clean", 0),
    })
    return {"step": "check", **result}


# ── 全量 Pipeline ──────────────────────────────────────────────────────────────

async def run_all(dataset_id: str) -> None:
    _set_status(dataset_id, "running", "process", 0, started_at=_now())
    try:
        r1 = await step_process(dataset_id)
        r2 = await step_pre_annotate(dataset_id)
        r3 = await step_embed(dataset_id)
        r4 = await step_check(dataset_id)
        _set_status(dataset_id, "completed", "", 100, finished_at=_now(),
                    results=[r1, r2, r3, r4])
    except Exception as e:
        _set_status(dataset_id, "error", "", 0, error=str(e), finished_at=_now())
        raise


async def run_step(dataset_id: str, step: str) -> dict[str, Any]:
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
        _set_status(dataset_id, "completed", step, 100, finished_at=_now(), results=result)
        return result
    except Exception as e:
        _set_status(dataset_id, "error", step, 0, error=str(e), finished_at=_now())
        raise
