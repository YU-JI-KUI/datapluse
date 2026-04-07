"""
Pipeline 引擎
流程：process → pre_annotate → (人工标注) → check → export

支持：
- 全量运行（run_all）
- 单步运行（run_step）
- 状态追踪（写入 NAS pipeline_status.json）
- 异步非阻塞（FastAPI BackgroundTasks）
- 详细进度：数量 / 百分比 / 速度 / ETA
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import get_settings
from modules.conflict import run_conflict_detection
from modules.embedding import embed_text
from modules.model import pre_annotate_batch
from modules.processing import process_item
from modules.vector import get_index, rebuild_index
from storage.nas import get_nas

STEPS = ["process", "pre_annotate", "embed", "check"]

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _set_status(
    status: str,
    step: str = "",
    progress: int = 0,
    detail: dict[str, Any] | None = None,
    **extra,
) -> None:
    nas = get_nas()
    data: dict[str, Any] = {
        "status": status,
        "current_step": step,
        "progress": progress,
        "detail": detail or {},
        "updated_at": _now(),
        **extra,
    }
    nas.set_pipeline_status(data)


def _make_detail(
    processed: int,
    total: int,
    skipped: int,
    start_time: float,
) -> dict[str, Any]:
    """构建进度详情字典"""
    elapsed = time.time() - start_time
    speed = processed / elapsed if elapsed > 0 else 0
    remaining = total - processed
    eta = int(remaining / speed) if speed > 0 else 0
    pct = processed / total * 100 if total > 0 else 0
    return {
        "processed": processed,
        "total": total,
        "skipped": skipped,
        "pct": f"{pct:.1f}%",
        "speed_per_sec": round(speed, 1),
        "eta_seconds": eta,
        "elapsed_seconds": round(elapsed, 1),
    }


# ── 单步执行 ──────────────────────────────────────────────────────────────────

async def step_process() -> dict[str, Any]:
    """清洗 raw → processed"""
    nas = get_nas()
    raw_items = nas.list_by_status("raw")
    total = len(raw_items)
    if total == 0:
        return {"step": "process", "processed": 0, "skipped": 0}

    start_time = time.time()
    skipped = 0
    nas.begin_bulk()
    try:
        for i, item in enumerate(raw_items):
            updated = process_item(item)
            if not updated:
                skipped += 1
                continue
            nas.update(updated)
            detail = _make_detail(i + 1, total, skipped, start_time)
            _set_status("running", "process", int((i + 1) / total * 100), detail=detail)
    finally:
        nas.end_bulk()

    return {"step": "process", "processed": total - skipped, "skipped": skipped}


async def step_pre_annotate() -> dict[str, Any]:
    """预标注 processed → pre_annotated"""
    nas = get_nas()
    settings = get_settings()
    items = nas.list_by_status("processed")
    total = len(items)
    if total == 0:
        return {"step": "pre_annotate", "annotated": 0, "skipped": 0}

    batch_size = settings.pipeline_batch_size
    annotated = 0
    skipped = 0
    start_time = time.time()

    nas.begin_bulk()
    try:
        for i in range(0, total, batch_size):
            batch = items[i: i + batch_size]
            results = await pre_annotate_batch(batch)
            for r in results:
                nas.update(r)
            annotated += len(results)
            detail = _make_detail(annotated, total, skipped, start_time)
            _set_status(
                "running", "pre_annotate",
                int(annotated / total * 100),
                detail=detail,
            )
    finally:
        nas.end_bulk()

    return {"step": "pre_annotate", "annotated": annotated, "skipped": skipped}


async def step_embed() -> dict[str, Any]:
    """为 pre_annotated / labeled 数据生成 embedding 并构建 FAISS 索引"""
    nas = get_nas()
    target_statuses = ["pre_annotated", "labeled", "checked"]
    items = []
    for s in target_statuses:
        items.extend(nas.list_by_status(s))

    total = len(items)
    if total == 0:
        return {"step": "embed", "embedded": 0, "skipped": 0}

    embedded = 0
    skipped = 0
    start_time = time.time()

    for i, item in enumerate(items):
        if nas.load_embedding(item["id"]) is not None:
            skipped += 1
            embedded += 1
        else:
            vec = embed_text(item["text"])
            nas.save_embedding(item["id"], vec)
            embedded += 1
        detail = _make_detail(embedded, total, skipped, start_time)
        _set_status("running", "embed", int(embedded / total * 100), detail=detail)

    # 重建向量索引
    count = rebuild_index()
    return {"step": "embed", "embedded": embedded, "skipped": skipped, "index_size": count}


async def step_check() -> dict[str, Any]:
    """冲突检测 labeled → checked"""
    _set_status("running", "check", 10, detail={"pct": "10%", "total": 0})
    result = await run_conflict_detection()
    total = result.get("total", 0)
    detail = {
        "total": total,
        "pct": "100%",
        "label_conflicts": result.get("label_conflicts", 0),
        "semantic_conflicts": result.get("semantic_conflicts", 0),
        "clean": result.get("clean", 0),
    }
    _set_status("running", "check", 100, detail=detail)
    return {"step": "check", **result}


# ── 全量 Pipeline ──────────────────────────────────────────────────────────────

async def run_all() -> None:
    """全量运行所有步骤（供 BackgroundTasks 调用）"""
    _set_status("running", "process", 0, started_at=_now())
    try:
        r1 = await step_process()
        r2 = await step_pre_annotate()
        r3 = await step_embed()
        r4 = await step_check()
        _set_status(
            "completed",
            "",
            100,
            finished_at=_now(),
            results=[r1, r2, r3, r4],
        )
    except Exception as e:
        _set_status("error", "", 0, error=str(e), finished_at=_now())
        raise


async def run_step(step: str) -> dict[str, Any]:
    """运行单个步骤"""
    if step not in STEPS:
        raise ValueError(f"未知步骤: {step}，可选: {STEPS}")

    _set_status("running", step, 0, started_at=_now())
    try:
        if step == "process":
            result = await step_process()
        elif step == "pre_annotate":
            result = await step_pre_annotate()
        elif step == "embed":
            result = await step_embed()
        elif step == "check":
            result = await step_check()
        else:
            raise ValueError(f"步骤 {step} 未实现")

        _set_status("completed", step, 100, finished_at=_now(), results=result)
        return result
    except Exception as e:
        _set_status("error", step, 0, error=str(e), finished_at=_now())
        raise
