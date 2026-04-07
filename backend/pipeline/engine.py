"""
Pipeline 引擎
流程：process → pre_annotate → (人工标注) → check → export

支持：
- 全量运行（run_all）
- 单步运行（run_step）
- 状态追踪（写入 NAS pipeline_status.json）
- 异步非阻塞（FastAPI BackgroundTasks）
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from config.settings import get_settings
from modules.conflict import run_conflict_detection
from modules.embedding import embed_text
from modules.model import pre_annotate_batch
from modules.processing import process_item
from modules.vector import get_index, rebuild_index
from storage.nas import get_nas

STEPS = ["process", "pre_annotate", "embed", "check"]


def _now() -> str:
    return datetime.utcnow().isoformat()


def _set_status(status: str, step: str = "", progress: int = 0, **extra) -> None:
    nas = get_nas()
    data: dict[str, Any] = {
        "status": status,
        "current_step": step,
        "progress": progress,
        "updated_at": _now(),
        **extra,
    }
    nas.set_pipeline_status(data)


# ── 单步执行 ───────────────────────────────────────────────────────────────

async def step_process() -> dict[str, Any]:
    """清洗 raw → processed"""
    nas = get_nas()
    raw_items = nas.list_by_status("raw")
    total = len(raw_items)
    if total == 0:
        return {"step": "process", "processed": 0}

    for i, item in enumerate(raw_items):
        updated = process_item(item)
        nas.update(updated)
        _set_status("running", "process", int((i + 1) / total * 100))

    return {"step": "process", "processed": total}


async def step_pre_annotate() -> dict[str, Any]:
    """预标注 processed → pre_annotated"""
    nas = get_nas()
    settings = get_settings()
    items = nas.list_by_status("processed")
    total = len(items)
    if total == 0:
        return {"step": "pre_annotate", "annotated": 0}

    batch_size = settings.pipeline_batch_size
    annotated = 0
    for i in range(0, total, batch_size):
        batch = items[i : i + batch_size]
        results = await pre_annotate_batch(batch)
        for r in results:
            nas.update(r)
        annotated += len(results)
        _set_status("running", "pre_annotate", int(annotated / total * 100))

    return {"step": "pre_annotate", "annotated": annotated}


async def step_embed() -> dict[str, Any]:
    """为 pre_annotated / labeled 数据生成 embedding 并构建 FAISS 索引"""
    nas = get_nas()
    target_statuses = ["pre_annotated", "labeled", "checked"]
    items = []
    for s in target_statuses:
        items.extend(nas.list_by_status(s))

    total = len(items)
    if total == 0:
        return {"step": "embed", "embedded": 0}

    embedded = 0
    for i, item in enumerate(items):
        # 跳过已有 embedding 的
        if nas.load_embedding(item["id"]) is not None:
            embedded += 1
            continue
        vec = embed_text(item["text"])
        nas.save_embedding(item["id"], vec)
        embedded += 1
        _set_status("running", "embed", int(embedded / total * 100))

    # 重建向量索引
    count = rebuild_index()
    return {"step": "embed", "embedded": embedded, "index_size": count}


async def step_check() -> dict[str, Any]:
    """冲突检测 labeled → checked"""
    _set_status("running", "check", 10)
    result = await run_conflict_detection()
    _set_status("running", "check", 100)
    return {"step": "check", **result}


# ── 全量 Pipeline ──────────────────────────────────────────────────────────

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
