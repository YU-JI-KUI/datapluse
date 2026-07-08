"""AI 对话评测任务引擎。

接收上传文件 → 后台异步跑评测 → 逐条落盘 + 上报进度 → 结果持久化 → 导出报告。
任务跑一半中断可断点续跑（resume，只补未完成的行）。

对齐 datapulse 任务风格：进度状态写 t_eval_task 表，前端轮询；
后台执行用 BackgroundTasks（同步入口 run_eval_sync 内部 asyncio.run）。
核心评测逻辑在 datapulse.modules.eval.evaluator，本文件只做编排与持久化。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import structlog

from datapulse.config.settings import get_settings
from datapulse.modules.eval import eval_db
from datapulse.modules.eval.bu.registry import get_bu
from datapulse.modules.eval.evaluator import run_evaluation
from datapulse.modules.eval.llm.judge_runner import EvalCancelled, EvalPaused, RateLimitedError

_log = structlog.get_logger(__name__)
_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 限流暂停后，延迟多久自动重新入队续跑（秒）
_RATE_LIMIT_RESUME_DELAY = 120


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _public(t: dict) -> dict:
    """把任务行转成对外状态（含进度百分比、BU 展示名、后端类型）。"""
    settings = get_settings()
    total = t.get("progress_total") or 0
    done = t.get("progress_done") or 0
    pct = round(done / total * 100, 1) if total else 0.0
    bu_code = t.get("bu") or get_bu(None).code
    return {
        "task_id":        t["task_id"],
        "filename":       t["filename"],
        "bu":             bu_code,
        "bu_name":        get_bu(bu_code).name,
        "status":         t["status"],
        "stage":          t.get("stage") or "",
        "mode":           t.get("mode") or "",
        "progress_done":  done,
        "progress_total": total,
        "progress_pct":   pct,
        "created_at":     t.get("created_at"),
        "started_at":     t.get("started_at"),   # 真正开跑时间（排队等待不计入）
        "finished_at":    t.get("finished_at"),
        "created_by":     t.get("created_by") or "",   # 评测发起人
        "error":          t.get("error"),
        "backend":        settings.judge_backend,
    }


# ── 任务编排 ──────────────────────────────────────────────────────────────────

def create_task(filename: str, file_path: str, bu: str, created_by: str = "system") -> dict:
    task_id = uuid.uuid4().hex[:12]
    eval_db.create_task(task_id, filename, file_path, bu, created_by=created_by)
    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    t = eval_db.get_task(task_id)
    return _public(t) if t else None


def list_tasks_paged(page: int, page_size: int, bu: str = "",
                     keyword: str = "", mode: str = "") -> tuple[list[dict], int]:
    """分页任务列表(SQL 层分页 + 过滤),返回 (对外状态列表, 总数)。

    keyword 按文件名模糊匹配,mode 按评测模式(calibration/production)精确过滤。
    """
    rows, total = eval_db.list_tasks_paged(page, page_size, bu=bu, keyword=keyword, mode=mode)
    return [_public(t) for t in rows], total


def _display_sanitize(rows: list[dict], bu: str) -> list[dict]:
    """展示前对每条 answer_text 兜底净化（用与喂模型相同的规则，幂等）。

    新任务落盘时 answer_text 已净化、再跑无变化；老任务（净化器上线前评的）落的是
    原文，这里把它净化成模型口径，详情页就不再展示整坨 JSON。原地改 row。
    """
    from datapulse.modules.eval.answer_sanitizer import sanitize_answer
    for r in rows:
        if isinstance(r, dict) and isinstance(r.get("answer_text"), str):
            r["answer_text"] = sanitize_answer(r["answer_text"], bu)
    return rows


def _task_bu(task_id: str) -> str:
    t = eval_db.get_task(task_id)
    return (t or {}).get("bu") or ""


def get_result(task_id: str) -> dict | None:
    result = eval_db.load_result(task_id)
    if not result:
        return None
    # 叠加人工复核：把复核覆盖应用到指标上（最终值口径），实时重算分发准确率/解决率/需复核数。
    # 复核是小集合，只按其 row_index 批量取 AI 原判做增量，不重扫全量 rows。
    result = _apply_reviews(task_id, result)
    if result.get("disagreements"):
        _display_sanitize(result["disagreements"], _task_bu(task_id))
    return result


def _apply_reviews(task_id: str, result: dict) -> dict:
    from datapulse.modules.eval.evaluator import apply_reviews_to_result
    reviews = eval_db.review_list(task_id)
    if not reviews:
        result["summary"]["reviewed_count"] = 0
        return result
    ai_rows = eval_db.load_rows_by_indices(task_id, [r["row_index"] for r in reviews])
    return apply_reviews_to_result(result, reviews, ai_rows)


def _attach_reviews(task_id: str, rows: list[dict]) -> list[dict]:
    """给明细行附 review 字段（该行的人工复核覆盖），供详情页显示已复核状态与复核值。
    只按当前页 row_index 批量取，不全量加载。原地改 row。"""
    if not rows:
        return rows
    # 复核是少量子集，全量取一次建索引即可（远小于明细总量）
    review_map = {rv["row_index"]: rv for rv in eval_db.review_list(task_id)}
    for r in rows:
        r["review"] = review_map.get(r["row_index"])   # 无复核则 None
    return rows


def list_rows(task_id: str, page: int, page_size: int, filters: dict) -> list[dict]:
    """分页读逐条评测明细（前端结果页表格用），支持多字段过滤。"""
    rows = eval_db.load_rows_filtered(task_id, page, page_size, filters)
    rows = _display_sanitize(rows, _task_bu(task_id))
    return _attach_reviews(task_id, rows)


def count_rows(task_id: str, filters: dict) -> int:
    return eval_db.count_rows_filtered(task_id, filters)


def list_review_rows(task_id: str) -> list[dict]:
    """需复核子集（有限上限），供前端「需复核」过滤。"""
    rows = eval_db.load_review_rows(task_id)
    rows = _display_sanitize(rows, _task_bu(task_id))
    return _attach_reviews(task_id, rows)


def submit_review(task_id: str, row_index: int, *, reviewed_dispatch: str = "",
                  reviewed_resolved: str = "", reviewed_intent: str = "",
                  comment: str = "", reviewer: str = "system") -> dict:
    return eval_db.review_upsert(
        task_id, row_index, reviewed_dispatch=reviewed_dispatch,
        reviewed_resolved=reviewed_resolved, reviewed_intent=reviewed_intent,
        comment=comment, reviewer=reviewer)


def delete_review(task_id: str, row_index: int) -> bool:
    return eval_db.review_delete(task_id, row_index)


# 单次重跑上限:防误选全量。可选很大子集,但超过此数提示走全量重测更合适。
_RERUN_ROWS_MAX = 2000
# 重跑分批大小(与评测同口径,喂满并发)
_RERUN_BATCH = 50


async def _rerun_indices_core(task_id: str, indices: list[int], operator: str,
                              on_progress=None) -> int:
    """对给定 row_index 列表用最新提示词重 judge、覆盖、全量重算指标。返回重跑条数。

    调用方保证已排除已复核行、已持有 advisory 锁。分批跑并回调进度。
    """
    from datapulse.modules.eval.evaluator import (
        assemble_row,
        other_label,
        recompute_result_from_rows,
    )
    from datapulse.modules.eval.judge import assemble_row_sample_from_row
    from datapulse.modules.eval.llm.judge_runner import judge_batch

    t = eval_db.get_task(task_id)
    bu = get_bu(t.get("bu"))            # 注入最新 prompt/业务知识/分类快照
    allowed = set(bu.intents.keys())
    other = other_label(bu)

    done = 0
    total = len(indices)
    for start in range(0, total, _RERUN_BATCH):
        chunk = indices[start:start + _RERUN_BATCH]
        row_map = eval_db.load_rows_by_indices(task_id, chunk)
        samples = [assemble_row_sample_from_row(row_map[i]) for i in chunk if i in row_map]
        if not samples:
            continue
        judges = await judge_batch(samples, bu)
        new_rows = [assemble_row(s, j, allowed, other) for s, j in zip(samples, judges)]
        eval_db.save_rows(task_id, new_rows, created_by=operator)
        done += len(new_rows)
        if on_progress:
            on_progress(done, total)

    # 全量重算 summary(扫全表聚合,不调 LLM),覆盖 result_json
    old = eval_db.load_result(task_id) or {}
    mode = old.get("mode") or (old.get("summary", {}) or {}).get("mode") or "production"
    new_result = recompute_result_from_rows(old, eval_db.iter_all_row_jsons(task_id), mode)
    eval_db.save_result(task_id, new_result, updated_by=operator)
    return done


def rerun_rows_async(task_id: str, row_indices: list[int], operator: str = "system") -> dict:
    """异步重跑用户勾选的明细行(后台线程,不阻塞请求)。立即返回,前端轮询任务状态看进度。

    排除已复核行(人工结论优先);拿全局 advisory 锁与评测串行(不抢 LLM);
    任务 status 置 rerunning + progress 显示重跑进度,完成恢复 done。返回 {accepted, count}。
    """
    import asyncio
    import threading

    t = eval_db.get_task(task_id)
    if not t:
        return {"error": "任务不存在"}
    # 排除已复核的行(人工结论优先,不被自动覆盖)
    reviewed = {r["row_index"] for r in eval_db.review_list(task_id)}
    indices = sorted(set(row_indices) - reviewed)
    if not indices:
        return {"accepted": False, "count": 0, "reason": "所选行均已人工复核,无需重跑"}
    if len(indices) > _RERUN_ROWS_MAX:
        return {"accepted": False, "count": len(indices), "over_limit": True,
                "limit": _RERUN_ROWS_MAX}

    def _worker():
        from datapulse.modules.eval import eval_db as _db
        try:
            with _db.advisory_lock() as got:
                if not got:
                    eval_db.update_task(task_id, updated_by=operator,
                                        error="有评测任务正在运行，重跑未开始，请稍后再试")
                    return
                eval_db.update_task(task_id, updated_by=operator, status="rerunning",
                                    stage="rerunning", error=None,
                                    progress_done=0, progress_total=len(indices))

                def on_progress(done, total):
                    eval_db.update_task(task_id, updated_by=operator,
                                        progress_done=done, progress_total=total)

                reran = asyncio.run(_rerun_indices_core(task_id, indices, operator, on_progress))
                # 恢复 done 态,进度回填真实样本数
                samples = (eval_db.load_result(task_id) or {}).get("summary", {}).get("total_samples", reran)
                eval_db.update_task(task_id, updated_by=operator, status="done", stage="done",
                                    progress_done=samples, progress_total=samples)
                _log.info("eval.rerun_rows.done", task_id=task_id, reran=reran)
        except Exception as e:
            _log.exception("eval.rerun_rows.failed", task_id=task_id)
            eval_db.update_task(task_id, updated_by=operator, status="done",
                                error=f"重跑失败：{e}")

    threading.Thread(target=_worker, name=f"eval-rerun-{task_id}", daemon=True).start()
    return {"accepted": True, "count": len(indices)}


def rerun_subset(task_id: str, flag: str = "review", operator: str = "system") -> dict:
    """按筛选(flag=review 待复核)异步重跑该子集。薄封装:查 indices → rerun_rows_async。"""
    if not eval_db.get_task(task_id):
        return {"error": "任务不存在"}
    indices = eval_db.rerun_subset_indices(task_id, flag)
    return rerun_rows_async(task_id, indices, operator=operator)


async def _rerun_advice_core(task_id: str, operator: str) -> None:
    """只重算优化建议:复用已落盘 rows,不碰 judge/指标。用库中最新 advice 提示词。

    调优提示词后无需重跑整个评测:读回 rows 重聚合归因料 + 从 result_json 读回
    insights(judge 未变,口径不变),重新生成 advice,只覆盖 result_json 的 advice 字段。
    """
    from datapulse.modules.eval.advice_facts import build_facts
    from datapulse.modules.eval.llm.judge_runner import generate_advice

    t = eval_db.get_task(task_id)
    bu = get_bu(t.get("bu"))                     # get_bu 已注入库中最新 prompt/分类/业务知识
    old = eval_db.load_result(task_id) or {}
    bu_dispatch = (old.get("summary", {}) or {}).get("bu_dispatch") or old.get("bu_dispatch")
    insights = old.get("insights", {})           # judge 未重跑,直接复用,不重聚合
    facts = build_facts(task_id, bu, bu_dispatch)
    advice = await generate_advice(facts, insights, bu, bu_dispatch)
    old["advice"] = advice                       # 只替换 advice,其余字段原样写回
    eval_db.save_result(task_id, old, updated_by=operator)


def rerun_advice_async(task_id: str, operator: str = "system") -> dict:
    """异步单独重算优化建议(后台线程)。立即返回,前端轮询任务状态看进度。

    拿全局 advisory 锁与评测/重跑串行(advice 也并发调 LLM,不与大评测抢内网网关);
    不重 judge、不改 insights/metrics/summary。status 置 rerunning,完成恢复 done。
    """
    import threading

    t = eval_db.get_task(task_id)
    if not t:
        return {"error": "任务不存在"}
    if not eval_db.load_result(task_id):
        return {"accepted": False, "reason": "任务尚无评测结果,无法重算建议"}

    def _worker():
        from datapulse.modules.eval import eval_db as _db
        try:
            with _db.advisory_lock() as got:
                if not got:
                    eval_db.update_task(task_id, updated_by=operator,
                                        error="有评测任务正在运行，重算建议未开始，请稍后再试")
                    return
                eval_db.update_task(task_id, updated_by=operator, status="rerunning",
                                    stage="advising", error=None)
                asyncio.run(_rerun_advice_core(task_id, operator))
                eval_db.update_task(task_id, updated_by=operator, status="done", stage="done")
                _log.info("eval.rerun_advice.done", task_id=task_id)
        except Exception as e:
            _log.exception("eval.rerun_advice.failed", task_id=task_id)
            eval_db.update_task(task_id, updated_by=operator, status="done",
                                error=f"重算建议失败：{e}")

    threading.Thread(target=_worker, name=f"eval-advice-{task_id}", daemon=True).start()
    return {"accepted": True}


async def dryrun_row(task_id: str, row_index: int,
                     business_knowledge: str | None = None) -> dict | None:
    """用当前 prompt 对某一条重新跑 Judge,返回新旧对比,不落库。

    business_knowledge 非 None 时,用这段「临时业务知识」覆盖库里的版本参与试跑——
    支持详情页「编辑→试跑→满意再保存」:试跑时改动还没落库。None 则用库里已保存的。
    试跑结果不影响已落盘结果与指标。返回 {old, new, changed}。
    """
    from dataclasses import replace as _replace

    from datapulse.modules.eval.judge import assemble_row_sample_from_row
    from datapulse.modules.eval.llm.judge_runner import judge_one

    rows = eval_db.load_rows_by_indices(task_id, [row_index])
    row = rows.get(row_index)
    if not row:
        return None
    # get_bu 已注入库中最新全套 prompt(judge_system / 各 task / 分类 / 业务知识)。
    bu = get_bu(_task_bu(task_id))
    if business_knowledge is not None:
        # 只把业务知识替换成编辑框的临时内容,其余槽位仍用库里当前值 → 试跑口径 =
        # 「库里所有其它提示词 + 最新业务知识」。
        snap = dict(bu.prompts or {})
        snap["business_knowledge.md"] = business_knowledge
        bu = _replace(bu, prompts=snap)
    sample = assemble_row_sample_from_row(row)
    new_judge = await judge_one(sample, bu)

    def _brief(j):
        j = j if isinstance(j, dict) else {}
        return {
            "should_dispatch_to_bu": j.get("should_dispatch_to_bu"),
            "business_type": j.get("business_type"),
            "answer_resolved": j.get("answer_resolved"),
            "needs_human_review": j.get("needs_human_review"),
            "resolved_reason": j.get("resolved_reason"),
            "dispatch_reason": j.get("dispatch_reason"),
        }

    old = row.get("judge") if isinstance(row.get("judge"), dict) else {}
    new_brief, old_brief = _brief(new_judge), _brief(old)
    changed = any(new_brief.get(k) != old_brief.get(k)
                  for k in ("should_dispatch_to_bu", "business_type", "answer_resolved"))
    return {"row_index": row_index, "old": old_brief, "new": new_brief,
            "new_full": new_judge, "changed": changed}


_RESUMABLE_STATUS = {"failed", "paused", "interrupted"}


def can_resume(task_id: str) -> bool:
    """未到 done 的中断态（failed/paused/interrupted）→ 可续跑。

    paused/interrupted 即使还没落盘行也允许续跑（从头跑）；failed 沿用原口径
    （需有已落盘行才有续跑意义）。
    """
    t = eval_db.get_task(task_id)
    if not t or t["status"] not in _RESUMABLE_STATUS:
        return False
    if t["status"] == "failed":
        return bool(eval_db.done_row_indices(task_id))
    return True


async def run_eval(task_id: str, resume: bool = False, operator: str = "eval") -> None:
    """后台跑评测。resume=True 时断点续跑（跳过已落盘行）。"""
    t = eval_db.get_task(task_id)
    if not t:
        return
    # 快照该 BU 评测要用的全部 prompt,贯穿整个任务:中途用户改 prompt 只影响下次评测,
    # 不会让同一任务前后用不同口径。intents(业务分类)已在 get_bu 时固化进 frozen
    # BUConfig,天然是快照,无需再处理。
    from dataclasses import replace as _replace

    from datapulse.modules.eval.prompt_loader import snapshot_for_bu
    bu = get_bu(t.get("bu"))
    bu = _replace(bu, prompts=snapshot_for_bu(bu.code))
    eval_db.update_task(task_id, updated_by=operator, status="running", error=None)

    def on_progress(stage: str, done: int, total: int):
        eval_db.update_task(task_id, updated_by=operator,
                            stage=stage, progress_done=done, progress_total=total)

    try:
        result = await run_evaluation(
            t["file_path"], bu, on_progress=on_progress, task_id=task_id, persist=True,
        )
        eval_db.save_result(task_id, result, updated_by=operator)
        # 进度在 advising 阶段最后上报的是 (1,1)，会把 progress_total 覆盖成 1；
        # 完成时回填真实样本数，列表才能显示正确的样本量。
        total_samples = result["summary"]["total_samples"]
        eval_db.update_task(
            task_id, updated_by=operator,
            status="done", stage="done", mode=result["mode"], finished_at=_now(),
            progress_done=total_samples, progress_total=total_samples,
        )
        _log.info("eval.done", task_id=task_id, samples=result["summary"]["total_samples"])
    except RateLimitedError as e:
        # 大模型限流：暂停任务（已落盘行不丢），延迟后自动重新入队续跑，不跑成全垃圾
        _log.warning("eval.paused.rate_limited", task_id=task_id, err=str(e))
        eval_db.update_task(task_id, updated_by=operator,
                            status="paused", stage="paused", error=f"大模型限流，已暂停自动重试：{e}")
        from datapulse.modules.eval import eval_worker
        eval_worker.schedule_resume(task_id, delay=_RATE_LIMIT_RESUME_DELAY, operator=operator)
    except EvalCancelled:
        # 任务被删（DB 记录已没）：什么都不写，finally 释放锁，worker 立即抢下一个
        _log.info("eval.cancelled", task_id=task_id)
    except EvalPaused:
        # 任务被手动暂停：状态已是 paused（暂停接口置的），这里不覆盖、不自动续跑，
        # 释放锁腾出算力，等用户手动恢复
        _log.info("eval.paused.manual", task_id=task_id)
    except Exception as e:
        _log.exception("eval.failed", task_id=task_id)
        eval_db.update_task(task_id, updated_by=operator,
                            status="failed", error=str(e), finished_at=_now())
    finally:
        # 本任务的事件循环即将随 asyncio.run 关闭,先释放绑定到它的 httpx 连接池,
        # 避免连接对象泄漏(client 按 loop 缓存,不关就一直留着旧循环的池)。
        from datapulse.modules.eval.llm.pingan_client import close_client
        await close_client()


def run_eval_sync(task_id: str, resume: bool = False, operator: str = "eval") -> None:
    """同步入口，供 FastAPI BackgroundTasks.add_task 使用（内部 asyncio.run）。"""
    asyncio.run(run_eval(task_id, resume=resume, operator=operator))


def recover_tasks() -> int:
    """启动时恢复未完成任务(多 POD 安全)。返回退回 pending 的任务数。

    DB 抢占模型下不再逐个入队:只把「确定没在跑」的 paused/interrupted 退回 pending,
    再回收一遍心跳超时的僵尸 running。退回后由任一 POD 的 worker 抢占续跑(跳过已落盘行)。
    关键:绝不无条件动 running——多 POD 下别的 POD 可能正跑着,误退回会打断它;running
    的存活交给心跳超时判定(reclaim_stale)。
    """
    from datapulse.modules.eval.eval_worker import _STALE_SEC

    requeued = eval_db.requeue_idle()
    reclaimed = eval_db.reclaim_stale(_STALE_SEC)
    n = requeued + reclaimed
    if n:
        _log.info("eval.recover.done", requeued=requeued, reclaimed=reclaimed)
    return n


def delete_task(task_id: str) -> bool:
    """删除评测任务（连逐条结果一起硬删）。返回是否删到了记录。

    若任务正在跑，worker 的中断检查点下一批回查 get_task_status 得 None 即中止、
    释放串行锁，新任务立即可抢——不再卡在已删任务上。
    """
    return eval_db.delete_task(task_id)


def pause_task(task_id: str) -> bool:
    """暂停任务：running/pending → paused。返回任务是否可暂停。

    running：worker 中断检查点下一批感知 paused 后中止、释放锁，腾出算力；已落盘行不丢。
    pending：直接置 paused，worker 只抢 pending，天然不会抢它。
    非这两态（done/failed 等）不可暂停。
    """
    t = eval_db.get_task(task_id)
    if not t or t["status"] not in ("running", "pending"):
        return False
    eval_db.update_task(task_id, status="paused", stage="paused",
                        error="已手动暂停，可随时恢复")
    return True


def resume_task(task_id: str) -> bool:
    """恢复任务：paused/interrupted → pending，worker 重抢后断点续跑（已落盘行跳过）。

    显式置 pending 是必须的——worker 只抢 pending，光起 worker 抢不到 paused 任务。
    """
    t = eval_db.get_task(task_id)
    if not t or t["status"] not in ("paused", "interrupted"):
        return False
    eval_db.update_task(task_id, status="pending", stage="", error=None)
    return True


def rerun_task(task_id: str) -> bool:
    """重测：清空已落盘结果并把任务重置为 pending，调用方再起后台跑。

    返回任务是否存在。重跑用当前提示词（提示词可能已被改过）。
    """
    t = eval_db.get_task(task_id)
    if not t:
        return False
    eval_db.clear_rows(task_id)
    eval_db.update_task(
        task_id, status="pending", stage="", mode="",
        progress_done=0, progress_total=0, error=None,
        started_at=None, finished_at=None,   # 重跑：开始/完成时间重新计（下次被抢占开跑时写新 started_at）
    )
    return True


# ── 导出 ──────────────────────────────────────────────────────────────────────

def _outputs_dir() -> Path:
    return Path(get_settings().eval_outputs_dir)


def _export_name(task_id: str, kind: str) -> str:
    """拼导出文件名：<原始上传文件名(去扩展名)>_<kind>_<task_id>.xlsx。

    如上传 abc.xlsx → abc_评估报告_<task_id>.xlsx。取 task.filename 去掉目录与扩展名;
    文件名可能含路径分隔/非法字符,统一净化(去 / \\ : 等);为空(如样例任务无名)时
    省略前缀,回退到原来的 <kind>_<task_id>.xlsx。task_id 作后缀保证唯一、不覆盖。
    """
    import re
    t = eval_db.get_task(task_id) or {}
    raw = (t.get("filename") or "").strip()
    stem = Path(raw).stem if raw else ""                 # abc.xlsx → abc；空 → ''
    stem = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip("_")  # 净化文件系统非法字符
    prefix = f"{stem}_" if stem else ""
    return f"{prefix}{kind}_{task_id}.xlsx"


def _stream_to_xlsx(out: Path, columns: list[str], row_iter) -> Path:
    """用 openpyxl write_only 模式逐行写 xlsx，常量内存。

    write_only 工作簿不在内存保留单元格对象，append 一行即落到底层流，
    5万~几十万行也不会撑爆内存（对比 pandas.to_excel 需全量建对象树）。
    row_iter 产出 dict，按 columns 顺序取值；缺失键写空串。
    单元格只接受标量，list/dict 等结构统一转字符串。
    """
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    ws = wb.create_sheet()
    ws.append(columns)
    for rec in row_iter:
        ws.append([_cell(rec.get(c, "")) for c in columns])
    wb.save(out)
    return out


def _cell(v: Any):
    """xlsx 单元格只接受标量；其余转字符串，None 归空。"""
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _iter_all_rows(task_id: str, batch_size: int = 1000):
    """游标分页迭代某任务全部逐条结果（按 row_index 升序）。

    用 row_index > 上批最大值 翻页（keyset 分页），每批走唯一索引定位，
    整体 O(N)；避免 OFFSET 分页导出到后段越翻越慢。
    """
    after = -1   # row_index 从 0 起，-1 保证取到第一条
    while True:
        batch = eval_db.load_rows_after(task_id, after, batch_size)
        if not batch:
            break
        for idx, row_json in batch:
            yield row_json
        after = batch[-1][0]
        if len(batch) < batch_size:
            break


def _disagreement_record(r: dict) -> dict:
    j = r["judge"] if isinstance(r["judge"], dict) else {}
    return {
        "会话ID": r["session"],
        "轮次": r["turn"],
        "客户问题": r["question"],
        "分发BU": r.get("dispatched_bu", ""),
        "Judge意图": r["j_intent"],
        "Judge分发判定": r["j_dispatch"],
        "打标-分发是否正确": r["gold"].get("dispatch", ""),
        "Judge解决度": r["j_resolved"],
        "打标-答案是否解决": r["gold"].get("resolved", ""),
        "Judge理由": j.get("dispatch_reason", ""),
        "答案文本": r["answer_text"],
        "需人工复核": j.get("needs_human_review", ""),
    }


_DISAGREEMENT_COLUMNS = [
    "会话ID", "轮次", "客户问题", "分发BU", "Judge意图", "Judge分发判定",
    "打标-分发是否正确", "Judge解决度", "打标-答案是否解决", "Judge理由",
    "答案文本", "需人工复核",
]


def export_disagreements(task_id: str) -> Path | None:
    """把不一致 case 导出成 Excel（流式写），返回文件路径。"""
    result = eval_db.load_result(task_id)
    if not result:
        return None
    out = _outputs_dir() / _export_name(task_id, "不一致case")
    return _stream_to_xlsx(
        out, _DISAGREEMENT_COLUMNS,
        (_disagreement_record(r) for r in result.get("disagreements", [])),
    )


def _row_record(r: dict) -> dict:
    j = r["judge"] if isinstance(r["judge"], dict) else {}
    return {
        "会话ID": r["session"],
        "轮次": r["turn"],
        "客户问题": r["question"],
        "业务分类": r["j_intent"],
        "分发场景": r.get("dispatch_scene", ""),
        "AI判该本BU接": j.get("should_dispatch_to_bu", ""),
        "实际分给本BU": r.get("dispatched_to_bu", ""),
        "分发判定理由": j.get("dispatch_reason", ""),
        "是否解决": r["j_resolved"],
        "解决度原值": r.get("j_resolved_raw", ""),
        "解决度理由": j.get("resolved_reason", ""),
        "未解决原因": j.get("unresolved_cause", ""),
        "需人工复核": j.get("needs_human_review", ""),
        "复核原因": j.get("review_reason", ""),
        "打标-分发是否正确": r["gold"].get("dispatch", ""),
        "打标-答案是否解决": r["gold"].get("resolved", ""),
        "答案原文": r["answer_text"],
    }


_ROW_COLUMNS = [
    "会话ID", "轮次", "客户问题", "业务分类", "分发场景",
    "AI判该本BU接", "实际分给本BU", "分发判定理由",
    "是否解决", "解决度原值", "解决度理由", "未解决原因",
    "需人工复核", "复核原因",
    "打标-分发是否正确", "打标-答案是否解决", "答案原文",
]


def export_rows(task_id: str) -> Path | None:
    """逐条评测明细全量导出 Excel：每条一行，含模型完整判断 + 答案原文。

    游标分页从 t_eval_task_row 流式读 + openpyxl write_only 流式写，常量内存，
    5万~几十万行稳定导出（不再全量建 records + DataFrame）。
    """
    if not eval_db.load_result(task_id):
        return None
    out = _outputs_dir() / _export_name(task_id, "评测明细")
    return _stream_to_xlsx(
        out, _ROW_COLUMNS,
        (_row_record(r) for r in _iter_all_rows(task_id)),
    )


def export_report(task_id: str) -> Path | None:
    """完整评估报告导出 Excel：概览 / BU分发漏斗 / 业务洞察切片 / 优化建议 多 sheet。"""
    result = eval_db.load_result(task_id)
    if not result:
        return None
    s = result["summary"]
    disp = s.get("bu_dispatch") or {}

    def pct(v):
        return f"{round((v or 0) * 100, 1)}%"

    overview = [
        ("业务单元(BU)", s.get("bu_name", "")),
        ("评测模式", "校准(有人工打标)" if result["mode"] == "calibration" else "生产(无标注)"),
        ("评测样本数", s.get("total_samples", 0)),
        ("会话数", s.get("sessions", 0)),
        ("多轮会话数", s.get("multi_turn_sessions", 0)),
        ("BU分发准确率", pct(s.get("dispatch_accuracy"))),
        ("问题解决率(仅分发到本BU)", pct(s.get("end_to_end_resolved_rate"))),
        ("需人工复核数", s.get("needs_review", 0)),
        ("评测出错数", s.get("errors", 0)),
    ]
    _scored = disp.get("scored", 0) or 1   # 比例分母（参与评分数），防除零
    _over = disp.get("over_should_reject_but_accepted", 0)
    _miss = disp.get("miss_should_accept_but_rejected", 0)
    dispatch = [
        ("参与评分条数", disp.get("scored", 0)),
        ("分发判对(AI判该接与实际一致)", disp.get("correct", 0)),
        ("分发判错", disp.get("wrong", 0)),
        ("BU分发准确率", pct(disp.get("accuracy"))),
        ("误收(该拒识却承接)", f"{_over}（{pct(_over / _scored)}）"),
        ("漏收(该承接却拒识)", f"{_miss}（{pct(_miss / _scored)}）"),
    ]
    _ins_total = sum(x["count"] for x in result["insights"]["by_intent"]) or 1
    slices = [
        {
            "业务分类": x["name"],
            "样本量": x["count"],
            "样本占比": pct(x["count"] / _ins_total),
            "实际分入本BU": x.get("in_bu_count", 0),
            "分入占比": pct((x.get("in_bu_count", 0)) / (x["count"] or 1)),
            "问题解决率": pct(x.get("resolved_rate")),
            "需复核率": pct(x.get("needs_review_rate")),
            "典型未解决问题": "；".join(x.get("unresolved_examples", [])[:3]),
        }
        for x in result["insights"]["by_intent"]
    ]
    advice = [
        {
            "作用域": a.get("scope", ""),
            "严重度": a.get("severity", ""),
            "问题": a.get("problem", ""),
            "根因": a.get("root_cause", ""),
            "建议动作": a.get("suggestion", ""),
            "依据": a.get("evidence", ""),
        }
        for a in result.get("advice", {}).get("items", [])
    ]

    out = _outputs_dir() / _export_name(task_id, "评估报告")
    with pd.ExcelWriter(out) as writer:
        pd.DataFrame(overview, columns=["指标", "数值"]).to_excel(writer, sheet_name="概览", index=False)
        pd.DataFrame(dispatch, columns=["指标", "数值"]).to_excel(writer, sheet_name="BU分发漏斗", index=False)
        pd.DataFrame(slices).to_excel(writer, sheet_name="业务洞察", index=False)
        adv_df = pd.DataFrame(advice) if advice else pd.DataFrame([{"说明": "本次无优化建议(指标良好或样本不足)"}])
        adv_df.to_excel(writer, sheet_name="优化建议", index=False)
    return out


# ── 提示词管理 ────────────────────────────────────────────────────────────────

# 模板名 → 中文用途说明（编辑页展示，让用户知道每个模板影响什么）
_PROMPT_DESC = {
    "judge_system.md":      "Judge 系统人设：评测专家身份与总体判定立场",
    "judge_user.md":        "Judge 用户模板：单条样本的输入拼装格式",
    "task_dispatch.md":     "任务·分发判定：该不该本 BU 承接",
    "task_business_type.md": "任务·业务分类：给客户问题打业务标签",
    "task_resolved.md":     "任务·解决判定：答案是否解决客户问题",
    "task_review.md":       "任务·人工复核：是否需要人工二次确认",
    "business_knowledge.md": "业务补充规则：业务方自己写的判定规则/领域知识，追加进 Judge（安全地盘，不碰技术模板）",
    "advice_card_system.md":       "优化建议·系统人设：多专项建议共用的顾问身份",
    "advice_dispatch_global.md":   "优化建议·分发诊断（全局）：漏收/误收归因",
    "advice_resolved_global.md":   "优化建议·解决率诊断（全局）：四归因分布",
    "advice_new_business.md":      "优化建议·新业务分类发现：非本 BU 问题聚类",
    "advice_intent_dispatch.md":   "优化建议·分类分发提升（逐分类，占位 {intent_name}）",
    "advice_intent_resolved.md":   "优化建议·分类解决率提升（逐分类，占位 {intent_name}）",
}


def _prompt_desc(name: str) -> str:
    return _PROMPT_DESC.get(name, "")


# BU 级模板槽位（每个 BU 都可单独覆盖；未覆盖则继承通用 _default/文件）
_BU_SLOTS = (
    "judge_system.md", "task_dispatch.md", "task_business_type.md",
    "task_resolved.md", "task_review.md", "business_knowledge.md",
    "advice_card_system.md",
    "advice_dispatch_global.md", "advice_resolved_global.md", "advice_new_business.md",
    "advice_intent_dispatch.md", "advice_intent_resolved.md",
)
# 根共享模板槽位（跨 BU 共用，作用域 _root）
_ROOT_SLOTS = ("judge_user.md",)

DEFAULT_SCOPE = "_default"
ROOT_SCOPE = "_root"


def list_prompts(bu: str) -> dict:
    """列出某 BU 的全部模板槽位 + 根共享槽位，标注每个的来源（专属/继承/根共享）。

    不再只列文件系统已有文件——每个 BU 固定列出全部槽位，缺失的也能新建专属覆盖，
    解决「某 BU 无法重写某模块」的问题。
    """
    custom = {(r["bu"], r["name"]): r for r in eval_db.prompt_list()}

    def slot(scope, name):
        own = custom.get((scope, name))          # 该作用域是否有库记录
        if scope == ROOT_SCOPE:
            source = "shared"                    # 根共享
        elif own:
            source = "own"                       # BU 专属覆盖
        else:
            source = "inherited"                 # 继承通用（_default / 文件）
        return {
            "bu": scope, "name": name, "description": _prompt_desc(name),
            "source": source,                    # own=专属 / inherited=继承通用 / shared=根共享
            "customized": own is not None,
            "updated_at": own["updated_at"] if own else None,
            "updated_by": own["updated_by"] if own else None,
        }

    return {
        "bu": bu,
        "own": [slot(bu, n) for n in _BU_SLOTS],        # 当前 BU 的全部槽位
        "shared": [slot(ROOT_SCOPE, n) for n in _ROOT_SLOTS],  # 跨 BU 共享
    }


def get_prompt(bu: str, name: str) -> dict | None:
    """单条详情：当前有效内容（库优先、继承通用、文件兜底）+ 文件出厂默认 + 来源。"""
    from datapulse.modules.eval import prompt_loader

    own = eval_db.prompt_get(bu, name)                 # 该 BU 的专属覆盖
    file_default = prompt_loader.file_default(bu, name)
    if own:
        content, source = own["content"], "own"
    elif bu == ROOT_SCOPE:
        content = file_default or prompt_loader.load_prompt(name)
        source = "shared"
    else:
        # 未专属：显示当前生效内容（继承通用），编辑保存即为本 BU 创建专属覆盖
        content = prompt_loader.load_bu_prompt(bu, name)
        source = "inherited"
    return {
        "bu": bu, "name": name, "description": _prompt_desc(name),
        "content": content,
        "file_default": file_default,
        "source": source,
        "customized": own is not None,
        "updated_at": own["updated_at"] if own else None,
        "updated_by": own["updated_by"] if own else None,
    }


def save_prompt(bu: str, name: str, content: str, operator: str = "system") -> dict:
    """保存提示词（upsert）并失效缓存，使下次评测即读到新值。"""
    from datapulse.modules.eval import prompt_loader

    rec = eval_db.prompt_upsert(bu, name, content,
                                      description=_prompt_desc(name), updated_by=operator)
    prompt_loader.bump_version()
    return rec


def reset_prompt(bu: str, name: str) -> bool:
    """重置为文件出厂默认（删库记录）并失效缓存。返回是否真的删了。"""
    from datapulse.modules.eval import prompt_loader

    deleted = eval_db.prompt_delete(bu, name)
    if deleted:
        prompt_loader.bump_version()
    return deleted


# ── 业务分类管理 ──────────────────────────────────────────────────────────────

def _bump_categories():
    from datapulse.modules.eval.bu.base import bump_categories_version
    bump_categories_version()


def list_categories(bu: str) -> list[dict]:
    return eval_db.category_list(bu)


def create_category(bu: str, name: str, definition: str, operator: str = "system") -> dict:
    rec = eval_db.category_create(bu, name, definition, created_by=operator)
    _bump_categories()
    return rec


def update_category(cat_id: int, name: str | None, definition: str | None,
                    operator: str = "system") -> dict | None:
    rec = eval_db.category_update(cat_id, name=name, definition=definition, updated_by=operator)
    _bump_categories()
    return rec


def delete_category(cat_id: int) -> bool:
    deleted = eval_db.category_delete(cat_id)
    if deleted:
        _bump_categories()
    return deleted


# ── 活动标问管理 ──────────────────────────────────────────────────────────────

def _bump_activity():
    from datapulse.modules.eval.bu.base import bump_activity_version
    bump_activity_version()


def list_activity_questions(bu: str) -> list[dict]:
    return eval_db.activity_list(bu)


def create_activity_question(bu: str, question: str, note: str = "", activity_name: str = "",
                             operator: str = "system") -> dict:
    rec = eval_db.activity_create(bu, question, note=note, activity_name=activity_name,
                                  created_by=operator)
    _bump_activity()
    return rec


def create_activity_questions(bu: str, questions: list[str], note: str = "",
                              activity_name: str = "", operator: str = "system") -> list[dict]:
    """批量新增：同一活动名下一次录入多条标问。去空、去重（保序），空列表直接返回。"""
    seen, items = set(), []
    for q in questions:
        q = (q or "").strip()
        if q and q not in seen:
            seen.add(q)
            items.append({"question": q, "activity_name": activity_name, "note": note})
    if not items:
        return []
    recs = eval_db.activity_create_many(bu, items, created_by=operator)
    _bump_activity()
    return recs


def update_activity_question(act_id: int, question: str, note: str = "", activity_name: str = "",
                             operator: str = "system") -> dict | None:
    rec = eval_db.activity_update(act_id, question, activity_name=activity_name,
                                  note=note, updated_by=operator)
    if rec:
        _bump_activity()
    return rec


def delete_activity_question(act_id: int) -> bool:
    deleted = eval_db.activity_delete(act_id)
    if deleted:
        _bump_activity()
    return deleted


# ── 规则短路管理 ──────────────────────────────────────────────────────────────

def _bump_rules():
    from datapulse.modules.eval.bu.base import bump_rules_version
    bump_rules_version()


def list_rules(bu: str) -> list[dict]:
    return eval_db.rule_list(bu)


def upsert_rule(bu: str, question: str, expected_answer: str, judge_json: dict,
                note: str = "", operator: str = "system") -> dict:
    rec = eval_db.rule_upsert(bu, question, expected_answer, judge_json,
                              note=note, updated_by=operator)
    _bump_rules()
    return rec


def delete_rule(rule_id: int) -> bool:
    deleted = eval_db.rule_delete(rule_id)
    if deleted:
        _bump_rules()
    return deleted


# ── 问题洞察 ───────────────────────────────────────────────────────────────────

def question_insights(bu: str, intent: str = "", start: str = "", end: str = "") -> dict:
    """高频问榜单（含占比）+ 每日提问频率。BU 跟随顶栏，intent/时间为页面内筛选。"""
    top, total = eval_db.agg_top_questions(bu, intent=intent, start=start, end=end, limit=100)
    for it in top:
        it["ratio"] = round(it["count"] / total, 4) if total else 0.0
    daily = eval_db.agg_daily_counts(bu, intent=intent, start=start, end=end)
    return {
        "bu": bu,
        "total": total,
        "distinct": len(top),
        "top_questions": top,
        "daily": daily,
    }


def keyword_insights(bu: str, intent: str = "", top_n: int = 15) -> dict:
    """按业务分类提炼高区分关键词（jieba + TF-IDF，纯展示）。"""
    from datapulse.modules.eval import keyword_extract

    rows, truncated = eval_db.agg_keyword_source(bu, intent=intent, limit_rows=20000)
    if truncated:
        _log.info("keyword_insights sampled (truncated)", bu=bu, intent=intent, limit=20000)
    groups = keyword_extract.extract_by_intent(rows, top_n=top_n)
    return {"bu": bu, "sampled": truncated, "sample_size": len(rows), "groups": groups}
