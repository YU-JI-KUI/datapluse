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


def list_tasks() -> list[dict]:
    return [_public(t) for t in eval_db.list_tasks()]


def get_result(task_id: str) -> dict | None:
    return eval_db.load_result(task_id)


def list_rows(task_id: str, page: int, page_size: int) -> list[dict]:
    """分页读逐条评测明细（前端结果页表格用）。"""
    return eval_db.load_rows_paged(task_id, page, page_size)


def count_rows(task_id: str) -> int:
    return eval_db.count_rows(task_id)


def list_review_rows(task_id: str) -> list[dict]:
    """需复核子集（有限上限），供前端「需复核」过滤。"""
    return eval_db.load_review_rows(task_id)


def can_resume(task_id: str) -> bool:
    """failed 且已有部分落盘 → 可续跑。"""
    t = eval_db.get_task(task_id)
    return bool(t and t["status"] == "failed" and eval_db.done_row_indices(task_id))


async def run_eval(task_id: str, resume: bool = False, operator: str = "eval") -> None:
    """后台跑评测。resume=True 时断点续跑（跳过已落盘行）。"""
    t = eval_db.get_task(task_id)
    if not t:
        return
    bu = get_bu(t.get("bu"))
    eval_db.update_task(task_id, updated_by=operator, status="running", error=None)

    def on_progress(stage: str, done: int, total: int):
        eval_db.update_task(task_id, updated_by=operator,
                            stage=stage, progress_done=done, progress_total=total)

    try:
        result = await run_evaluation(
            t["file_path"], bu, on_progress=on_progress, task_id=task_id, persist=True,
        )
        eval_db.save_result(task_id, result, updated_by=operator)
        eval_db.update_task(
            task_id, updated_by=operator,
            status="done", stage="done", mode=result["mode"], finished_at=_now(),
        )
        _log.info("eval.done", task_id=task_id, samples=result["summary"]["total_samples"])
    except Exception as e:
        _log.exception("eval.failed", task_id=task_id)
        eval_db.update_task(task_id, updated_by=operator,
                            status="failed", error=str(e), finished_at=_now())


def run_eval_sync(task_id: str, resume: bool = False, operator: str = "eval") -> None:
    """同步入口，供 FastAPI BackgroundTasks.add_task 使用（内部 asyncio.run）。"""
    asyncio.run(run_eval(task_id, resume=resume, operator=operator))


# ── 导出 ──────────────────────────────────────────────────────────────────────

def _outputs_dir() -> Path:
    return Path(get_settings().eval_outputs_dir)


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
    "会话ID", "轮次", "客户问题", "Judge意图", "Judge分发判定",
    "打标-分发是否正确", "Judge解决度", "打标-答案是否解决", "Judge理由",
    "答案文本", "需人工复核",
]


def export_disagreements(task_id: str) -> Path | None:
    """把不一致 case 导出成 Excel（流式写），返回文件路径。"""
    result = eval_db.load_result(task_id)
    if not result:
        return None
    out = _outputs_dir() / f"不一致case_{task_id}.xlsx"
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
    out = _outputs_dir() / f"评测明细_{task_id}.xlsx"
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
    dispatch = [
        ("参与评分条数", disp.get("scored", 0)),
        ("分发判对(AI判该接与实际一致)", disp.get("correct", 0)),
        ("分发判错", disp.get("wrong", 0)),
        ("BU分发准确率", pct(disp.get("accuracy"))),
        ("误收(该拒识却承接)", disp.get("over_should_reject_but_accepted", 0)),
        ("漏收(该承接却拒识)", disp.get("miss_should_accept_but_rejected", 0)),
    ]
    slices = [
        {
            "业务分类": x["name"],
            "样本量": x["count"],
            "进漏斗(分发到本BU)": x.get("in_bu_count", 0),
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

    out = _outputs_dir() / f"评估报告_{task_id}.xlsx"
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
    "advice_system.md":     "优化建议·系统人设：给建议的专家身份",
    "advice_user.md":       "优化建议·用户模板：喂入聚合指标的格式",
}


def _prompt_desc(name: str) -> str:
    return _PROMPT_DESC.get(name, "")


def list_prompts() -> list[dict]:
    """列出可编辑提示词清单：出厂模板叠加库里的自定义状态（不含全文，列表轻量）。"""
    from datapulse.modules.eval import prompt_loader

    custom = {(r["bu"], r["name"]): r for r in eval_db.prompt_list()}
    out = []
    for it in prompt_loader.list_editable():
        key = (it["bu"], it["name"])
        c = custom.get(key)
        out.append({
            "bu": it["bu"],
            "name": it["name"],
            "description": _prompt_desc(it["name"]),
            "customized": c is not None,           # 库里有记录=已被用户改过
            "updated_at": c["updated_at"] if c else None,
            "updated_by": c["updated_by"] if c else None,
        })
    return out


def get_prompt(bu: str, name: str) -> dict | None:
    """单条详情：当前有效内容 + 文件出厂默认（供对比/重置）+ 是否自定义。"""
    from datapulse.modules.eval import prompt_loader

    file_default = prompt_loader.file_default(bu, name)
    rec = eval_db.prompt_get(bu, name)
    if rec is None and file_default is None:
        return None
    return {
        "bu": bu,
        "name": name,
        "description": _prompt_desc(name),
        "content": rec["content"] if rec else file_default,
        "file_default": file_default,
        "customized": rec is not None,
        "updated_at": rec["updated_at"] if rec else None,
        "updated_by": rec["updated_by"] if rec else None,
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
