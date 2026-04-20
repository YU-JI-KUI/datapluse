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

import structlog

from datapulse.modules.conflict import run_conflict_detection
from datapulse.modules.embedding import embed_batch
from datapulse.modules.model import pre_annotate
from datapulse.modules.processing import process_item
from datapulse.modules.vector import rebuild_index
from datapulse.repository.base import get_db

_log = structlog.get_logger(__name__)

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
    operator: str = "pipeline",
    **extra: Any,
) -> None:
    db   = get_db()
    data: dict[str, Any] = {
        "status":       status,
        "current_step": step,
        "progress":     progress,
        "detail":       detail or {},
        "updated_at":   _now(),
        "updated_by":   operator,
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


async def step_process(dataset_id: int, operator: str = "pipeline") -> dict[str, Any]:
    """清洗 raw → cleaned

    优化：
      1. bulk_update_stage 一次 UPDATE 代替 N 次逐行 UPDATE
      2. _set_status 每 _STATUS_UPDATE_INTERVAL 条更新一次，减少 DB 写入
    """
    db         = get_db()
    raw_items  = db.list_data_by_status(dataset_id, "raw")
    total      = len(raw_items)
    if total == 0:
        _log.info("step=process skipped (no raw items)", dataset_id=dataset_id)
        return {"step": "process", "processed": 0, "skipped": 0}

    _log.info("step=process started", dataset_id=dataset_id, total=total)

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
                operator=operator,
            )

    # 一次 bulk UPDATE 代替 N 次逐行 update_stage
    db.bulk_update_stage(processed_ids, "cleaned", updated_by=operator)

    result = {"step": "process", "processed": total - skipped, "skipped": skipped}
    _log.info("step=process done", dataset_id=dataset_id, **result)
    return result


async def step_pre_annotate(dataset_id: int, operator: str = "pipeline") -> dict[str, Any]:
    """预标注 cleaned → pre_annotated（结果写入 t_pre_annotation）

    性能优化：
      1. asyncio.gather + Semaphore 并发调用 LLM，并发数由 llm.concurrency 控制。
         相比逐条串行 await，吞吐量提升与 concurrency 倍数正相关。
      2. 按 chunk_size 分块提交，控制单次 gather 的内存占用。
      3. 每 chunk 批量写 DB（一次 INSERT + 一次 UPDATE）。
    """
    import asyncio

    db         = get_db()
    cfg        = db.get_dataset_config(dataset_id)
    items      = db.list_data_by_status(dataset_id, "cleaned")
    total      = len(items)
    if total == 0:
        _log.info("step=pre_annotate skipped (no cleaned items)", dataset_id=dataset_id)
        return {"step": "pre_annotate", "annotated": 0, "skipped": 0}

    llm_cfg     = cfg.get("llm", {})
    model_name  = llm_cfg.get("model_name", "mock")
    use_mock    = llm_cfg.get("use_mock", True)
    concurrency = llm_cfg.get("concurrency", 8)
    chunk_size  = cfg.get("pipeline", {}).get("batch_size", 32) * 4  # 每轮 gather 的条数

    _log.info(
        "step=pre_annotate started",
        dataset_id=dataset_id, total=total,
        model=model_name, mock=use_mock, concurrency=concurrency,
    )

    sem        = asyncio.Semaphore(concurrency)
    annotated  = 0
    start_time = time.time()

    async def _annotate_one(item: dict[str, Any]) -> tuple[dict[str, Any], str, float, str]:
        async with sem:
            label, score, cot = await pre_annotate(item, cfg)
            return item, label, score, cot

    for chunk_start in range(0, total, chunk_size):
        chunk   = items[chunk_start : chunk_start + chunk_size]
        results = await asyncio.gather(*[_annotate_one(item) for item in chunk])

        pre_records: list[dict] = []
        batch_ids:   list[int]  = []
        for item, label, score, cot in results:
            data_id = item["id"]
            pre_records.append({
                "data_id":    data_id,
                "model_name": model_name,
                "label":      label,
                "score":      score,
                "cot":        cot or None,
                "created_by": operator,
            })
            batch_ids.append(data_id)
            annotated += 1

        db.bulk_create_pre_annotations(pre_records)
        db.bulk_update_stage(batch_ids, "pre_annotated", updated_by=operator)

        _set_status(
            dataset_id, "running", "pre_annotate",
            int(annotated / total * 100),
            detail=_make_detail(annotated, total, 0, start_time),
            operator=operator,
        )

    elapsed = round(time.time() - start_time, 1)
    result  = {"step": "pre_annotate", "annotated": annotated, "skipped": 0}
    _log.info("step=pre_annotate done", dataset_id=dataset_id, elapsed_s=elapsed, **result)
    return result


async def step_embed(dataset_id: int, operator: str = "pipeline") -> dict[str, Any]:
    """为 pre_annotated / annotated / checked 数据生成 embedding，向量批量写入 PostgreSQL。

    性能优化：
      1. get_existing_ids() 一次 DB 查询替代 N 次文件存在检查。
      2. embed_batch() 批量编码，充分利用 SentenceTransformer 的向量化加速（GPU/CPU）。
      3. bulk_save_embeddings() 批量 UPSERT（每批 64 条 → 约 1000 次 DB round-trip），
         彻底消除 NAS 逐文件 write（旧方案 60k × 50ms ≈ 50 min 的根本原因）。
    """
    db    = get_db()
    cfg   = db.get_dataset_config(dataset_id)
    items = []
    for stage in ["pre_annotated", "annotated", "checked"]:
        items.extend(db.list_data_by_status(dataset_id, stage))

    total = len(items)
    if total == 0:
        return {"step": "embed", "embedded": 0, "skipped": 0}

    use_mock   = cfg.get("embedding", {}).get("use_mock", True)
    batch_size = cfg.get("embedding", {}).get("batch_size", 64)
    _log.info("step=embed started", dataset_id=dataset_id, total=total,
              mock=use_mock, batch_size=batch_size)

    start_time = time.time()

    # 一次 DB 查询取出已向量化的 item_id，跳过重复计算
    existing_ids = db.get_existing_embedding_ids(dataset_id)
    to_embed     = [item for item in items if int(item["id"]) not in existing_ids]
    skipped      = len(items) - len(to_embed)

    _log.info("step=embed scan done", dataset_id=dataset_id,
              to_embed=len(to_embed), already_skipped=skipped)

    # 按 batch_size 批量编码，然后整批 UPSERT 到 PostgreSQL
    embedded = skipped
    for i in range(0, len(to_embed), batch_size):
        batch  = to_embed[i : i + batch_size]
        texts  = [item["content"] for item in batch]
        vecs   = embed_batch(texts, cfg)   # shape: (len(batch), dim)

        # 收集本批 (item_id, vector) 对，一次 bulk UPSERT（约 1 次 DB round-trip）
        pairs = [(int(item["id"]), vec) for item, vec in zip(batch, vecs)]
        db.bulk_save_embeddings(dataset_id, pairs, created_by=operator)
        embedded += len(batch)

        if embedded % _STATUS_UPDATE_INTERVAL < batch_size or embedded == total:
            _set_status(
                dataset_id, "running", "embed",
                int(embedded / total * 100),
                detail=_make_detail(embedded, total, skipped, start_time),
                operator=operator,
            )

    count   = rebuild_index(dataset_id)
    elapsed = round(time.time() - start_time, 1)
    result  = {"step": "embed", "embedded": embedded, "skipped": skipped, "index_size": count}
    _log.info("step=embed done", dataset_id=dataset_id, elapsed_s=elapsed, **result)
    return result


async def step_check(dataset_id: int, operator: str = "pipeline") -> dict[str, Any]:
    """冲突检测 annotated → checked（干净）或保持 annotated（有冲突）"""
    _set_status(dataset_id, "running", "check", 10,
                detail={"pct": "10%", "total": 0}, operator=operator)
    result = await run_conflict_detection(dataset_id, operator=operator)
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
        operator=operator,
    )
    return {"step": "check", **result}


# ── 全量 Pipeline ──────────────────────────────────────────────────────────────


async def run_all(dataset_id: int, operator: str = "pipeline") -> None:
    t0 = time.time()
    _log.info("pipeline started", dataset_id=dataset_id, operator=operator)
    _set_status(dataset_id, "running", "process", 0, started_at=_now(), operator=operator)
    try:
        r1 = await step_process(dataset_id, operator=operator)
        r2 = await step_pre_annotate(dataset_id, operator=operator)
        r3 = await step_embed(dataset_id, operator=operator)
        r4 = await step_check(dataset_id, operator=operator)
        elapsed = round(time.time() - t0, 1)
        _log.info(
            "pipeline completed",
            dataset_id=dataset_id, elapsed_s=elapsed,
            process=r1, pre_annotate=r2, embed=r3, check=r4,
        )
        _set_status(dataset_id, "completed", "", 100,
                    finished_at=_now(), results=[r1, r2, r3, r4], operator=operator)
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        _log.error("pipeline failed", dataset_id=dataset_id, elapsed_s=elapsed, error=str(e))
        _set_status(dataset_id, "error", "", 0, error=str(e), finished_at=_now(), operator=operator)
        raise


def run_all_sync(dataset_id: int, operator: str = "pipeline") -> None:
    """同步包装器，供 FastAPI BackgroundTasks 使用。

    BackgroundTasks 对 sync 函数会自动放到线程池（run_in_threadpool）执行，
    不会阻塞主 asyncio 事件循环。内部通过 asyncio.run() 创建独立事件循环，
    以支持 step_pre_annotate 中的 async LLM 调用。
    """
    import asyncio as _asyncio
    _asyncio.run(run_all(dataset_id, operator=operator))


async def run_step(dataset_id: int, step: str, operator: str = "pipeline") -> dict[str, Any]:
    if step not in STEPS:
        raise ValueError(f"未知步骤: {step}，可选: {STEPS}")

    _set_status(dataset_id, "running", step, 0, started_at=_now(), operator=operator)
    try:
        fn = {
            "process":      step_process,
            "pre_annotate": step_pre_annotate,
            "embed":        step_embed,
            "check":        step_check,
        }[step]
        result = await fn(dataset_id, operator=operator)
        _set_status(dataset_id, "completed", step, 100,
                    finished_at=_now(), results=result, operator=operator)
        return result
    except Exception as e:
        _log.error("pipeline step failed", dataset_id=dataset_id, step=step, error=str(e))
        _set_status(dataset_id, "error", step, 0,
                    error=str(e), finished_at=_now(), operator=operator)
        raise
