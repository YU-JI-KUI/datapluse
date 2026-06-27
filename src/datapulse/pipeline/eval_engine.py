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
from datapulse.modules.eval.bu.registry import get_bu
from datapulse.modules.eval.evaluator import run_evaluation
from datapulse.repository.base import get_db

_log = structlog.get_logger(__name__)
_SHANGHAI = ZoneInfo("Asia/Shanghai")


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
        "finished_at":    t.get("finished_at"),
        "error":          t.get("error"),
        "backend":        settings.judge_backend,
    }


# ── 任务编排 ──────────────────────────────────────────────────────────────────

def create_task(filename: str, file_path: str, bu: str, created_by: str = "system") -> dict:
    task_id = uuid.uuid4().hex[:12]
    db = get_db()
    db.eval_create_task(task_id, filename, file_path, bu, created_by=created_by)
    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    t = get_db().eval_get_task(task_id)
    return _public(t) if t else None


def list_tasks() -> list[dict]:
    return [_public(t) for t in get_db().eval_list_tasks()]


def get_result(task_id: str) -> dict | None:
    return get_db().eval_load_result(task_id)


def list_rows(task_id: str, page: int, page_size: int) -> list[dict]:
    """分页读逐条评测明细（前端结果页表格用）。"""
    return get_db().eval_load_rows_paged(task_id, page, page_size)


def count_rows(task_id: str) -> int:
    return get_db().eval_count_rows(task_id)


def list_review_rows(task_id: str) -> list[dict]:
    """需复核子集（有限上限），供前端「需复核」过滤。"""
    return get_db().eval_load_review_rows(task_id)


def can_resume(task_id: str) -> bool:
    """failed 且已有部分落盘 → 可续跑。"""
    db = get_db()
    t = db.eval_get_task(task_id)
    return bool(t and t["status"] == "failed" and db.eval_done_row_indices(task_id))


async def run_eval(task_id: str, resume: bool = False, operator: str = "eval") -> None:
    """后台跑评测。resume=True 时断点续跑（跳过已落盘行）。"""
    db = get_db()
    t = db.eval_get_task(task_id)
    if not t:
        return
    bu = get_bu(t.get("bu"))
    db.eval_update_task(task_id, updated_by=operator, status="running", error=None)

    def on_progress(stage: str, done: int, total: int):
        db.eval_update_task(task_id, updated_by=operator,
                            stage=stage, progress_done=done, progress_total=total)

    try:
        result = await run_evaluation(
            t["file_path"], bu, on_progress=on_progress, task_id=task_id, persist=True,
        )
        db.eval_save_result(task_id, result, updated_by=operator)
        db.eval_update_task(
            task_id, updated_by=operator,
            status="done", stage="done", mode=result["mode"], finished_at=_now(),
        )
        _log.info("eval.done", task_id=task_id, samples=result["summary"]["total_samples"])
    except Exception as e:
        _log.exception("eval.failed", task_id=task_id)
        db.eval_update_task(task_id, updated_by=operator,
                            status="failed", error=str(e), finished_at=_now())


def run_eval_sync(task_id: str, resume: bool = False, operator: str = "eval") -> None:
    """同步入口，供 FastAPI BackgroundTasks.add_task 使用（内部 asyncio.run）。"""
    asyncio.run(run_eval(task_id, resume=resume, operator=operator))


# ── 导出 ──────────────────────────────────────────────────────────────────────

def _outputs_dir() -> Path:
    return Path(get_settings().eval_outputs_dir)


def export_disagreements(task_id: str) -> Path | None:
    """把不一致 case 导出成 Excel，返回文件路径。"""
    result = get_db().eval_load_result(task_id)
    if not result:
        return None
    records: list[dict[str, Any]] = []
    for r in result.get("disagreements", []):
        j = r["judge"] if isinstance(r["judge"], dict) else {}
        records.append({
            "会话ID": r["session"],
            "轮次": r["turn"],
            "客户问题": r["question"],
            "Judge意图": r["j_intent"],
            "Judge分发判定": r["j_dispatch"],
            "金标-分发是否正确": r["gold"].get("dispatch", ""),
            "Judge解决度": r["j_resolved"],
            "金标-答案是否解决": r["gold"].get("resolved", ""),
            "Judge理由": j.get("dispatch_reason", ""),
            "答案文本": r["answer_text"],
            "需人工复核": j.get("needs_human_review", ""),
        })
    columns = [
        "会话ID", "轮次", "客户问题", "Judge意图", "Judge分发判定",
        "金标-分发是否正确", "Judge解决度", "金标-答案是否解决", "Judge理由",
        "答案文本", "需人工复核",
    ]
    df = pd.DataFrame(records, columns=columns)
    out = _outputs_dir() / f"不一致case_{task_id}.xlsx"
    df.to_excel(out, index=False)
    return out


def _iter_all_rows(task_id: str, batch_size: int = 1000):
    """分页迭代某任务的全部逐条结果（按 row_index）。导出用，避免一次性全量加载。"""
    db = get_db()
    page = 1
    while True:
        batch = db.eval_load_rows_paged(task_id, page, batch_size)
        if not batch:
            break
        yield from batch
        if len(batch) < batch_size:
            break
        page += 1


def export_rows(task_id: str) -> Path | None:
    """逐条评测明细全量导出 Excel：每条一行，含模型完整判断 + 答案原文。

    逐条数据从 t_eval_task_row 分页读取（不再依赖 load_result 附带 rows）。
    """
    if not get_db().eval_load_result(task_id):
        return None
    records: list[dict[str, Any]] = []
    for r in _iter_all_rows(task_id):
        j = r["judge"] if isinstance(r["judge"], dict) else {}
        records.append({
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
            "金标-分发是否正确": r["gold"].get("dispatch", ""),
            "金标-答案是否解决": r["gold"].get("resolved", ""),
            "答案原文": r["answer_text"],
        })
    columns = [
        "会话ID", "轮次", "客户问题", "业务分类", "分发场景",
        "AI判该本BU接", "实际分给本BU", "分发判定理由",
        "是否解决", "解决度原值", "解决度理由", "未解决原因",
        "需人工复核", "复核原因",
        "金标-分发是否正确", "金标-答案是否解决", "答案原文",
    ]
    df = pd.DataFrame(records, columns=columns)
    out = _outputs_dir() / f"评测明细_{task_id}.xlsx"
    df.to_excel(out, index=False)
    return out


def export_report(task_id: str) -> Path | None:
    """完整评估报告导出 Excel：概览 / BU分发漏斗 / 业务洞察切片 / 优化建议 多 sheet。"""
    result = get_db().eval_load_result(task_id)
    if not result:
        return None
    s = result["summary"]
    disp = s.get("bu_dispatch") or {}

    def pct(v):
        return f"{round((v or 0) * 100, 1)}%"

    overview = [
        ("业务单元(BU)", s.get("bu_name", "")),
        ("评测模式", "校准(有人工金标)" if result["mode"] == "calibration" else "生产(无标注)"),
        ("评测样本数", s.get("total_samples", 0)),
        ("会话数", s.get("sessions", 0)),
        ("多轮会话数", s.get("multi_turn_sessions", 0)),
        ("BU分发准确率", pct(s.get("dispatch_accuracy"))),
        ("端到端解决率(仅分发到本BU)", pct(s.get("end_to_end_resolved_rate"))),
        ("需人工复核数", s.get("needs_review", 0)),
        ("评测出错数", s.get("errors", 0)),
    ]
    dispatch = [
        ("参与评分条数", disp.get("scored", 0)),
        ("分发判对", disp.get("correct", 0)),
        ("分发判错", disp.get("wrong", 0)),
        ("准确率", pct(disp.get("accuracy"))),
        ("该拒未拒(误收)", disp.get("over_should_reject_but_accepted", 0)),
        ("该分未分(漏收)", disp.get("miss_should_accept_but_rejected", 0)),
    ]
    slices = [
        {
            "业务分类": x["name"],
            "样本量": x["count"],
            "进漏斗(分发到本BU)": x.get("in_bu_count", 0),
            "端到端解决率": pct(x.get("resolved_rate")),
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

    out = _outputs_dir() / f"评估报告_{task_id}.xlsx"
    with pd.ExcelWriter(out) as writer:
        pd.DataFrame(overview, columns=["指标", "数值"]).to_excel(writer, sheet_name="概览", index=False)
        pd.DataFrame(dispatch, columns=["指标", "数值"]).to_excel(writer, sheet_name="BU分发漏斗", index=False)
        pd.DataFrame(slices).to_excel(writer, sheet_name="业务洞察", index=False)
        adv_df = pd.DataFrame(advice) if advice else pd.DataFrame([{"说明": "本次无优化建议(指标良好或样本不足)"}])
        adv_df.to_excel(writer, sheet_name="优化建议", index=False)
    return out
