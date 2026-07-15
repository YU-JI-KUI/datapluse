"""Eval repository — t_eval_task / t_eval_task_row

AI 对话评测的持久化层（独立于标注数据集）。逐条结果落盘后，任务跑一半中断
可断点续跑（只补未完成的行）。JSON 列用 JSONB（可查询/索引）。

由 ark-dialog-eval 的 services/store.py 平移而来，对外函数语义保持等价，
适配 datapulse 规范：id BIGSERIAL 主键、TIMESTAMP 审计字段、ISO 时间出参。
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from datapulse.modules.eval.entities import (
    EvalActivityQuestion,
    EvalCategory,
    EvalPrompt,
    EvalReview,
    EvalRule,
    EvalTask,
    EvalTaskRow,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _clean_json(obj):
    """递归把 inf/-inf/nan 替换成 None。PostgreSQL JSONB 不接受这些（不是合法 JSON
    数值），落盘前必须清掉，否则整条 insert 报 invalid input syntax for type json。"""
    if isinstance(obj, float):
        return None if (math.isinf(obj) or math.isnan(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_json(v) for v in obj]
    return obj


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# 任务元数据对外暴露的列（list_tasks 用，不含大字段 result_json）
_TASK_PUBLIC_KEYS = (
    "id", "task_id", "filename", "bu", "status", "stage", "mode",
    "progress_done", "progress_total", "error", "created_by",
)


def _task_to_dict(t: EvalTask, *, full: bool = False) -> dict[str, Any]:
    d: dict[str, Any] = {k: getattr(t, k) for k in _TASK_PUBLIC_KEYS}
    d["created_at"] = _iso(t.created_at)
    d["started_at"] = _iso(t.started_at)
    d["finished_at"] = _iso(t.finished_at)
    if full:
        d["file_path"] = t.file_path
        d["result_json"] = t.result_json
    return d


class EvalRepository:
    """Repository for EvalTask / EvalTaskRow entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── 任务元数据 ────────────────────────────────────────────────────────────

    def create_task(self, task_id: str, filename: str, file_path: str, bu: str,
                    created_by: str = "system") -> None:
        """INSERT ... ON CONFLICT DO UPDATE（重新触发同一 task_id 时重置为 pending）。"""
        ts = _now()
        stmt = pg_insert(EvalTask).values(
            task_id=task_id, filename=filename, file_path=file_path, bu=bu,
            status="pending", stage="",
            created_at=ts, created_by=created_by, updated_at=ts, updated_by=created_by,
        ).on_conflict_do_update(
            index_elements=["task_id"],
            set_={"filename": filename, "file_path": file_path, "bu": bu,
                  "status": "pending", "stage": "", "updated_at": ts, "updated_by": created_by},
        )
        self.session.execute(stmt)

    def update_task(self, task_id: str, updated_by: str = "system", **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _now()
        fields["updated_by"] = updated_by
        self.session.query(EvalTask).filter(EvalTask.task_id == task_id).update(fields)

    def get_task(self, task_id: str) -> dict | None:
        t = self.session.query(EvalTask).filter(EvalTask.task_id == task_id).first()
        return _task_to_dict(t, full=True) if t else None

    def get_task_status(self, task_id: str) -> str | None:
        """只取 status 一列（供评测循环的中断检查点每批轻量回查）。记录不存在返回 None。"""
        row = self.session.execute(
            select(EvalTask.status).where(EvalTask.task_id == task_id)
        ).first()
        return row[0] if row else None

    def list_tasks_paged(self, page: int, page_size: int, bu: str = "",
                         keyword: str = "", mode: str = "") -> tuple[list[dict], int]:
        """分页查任务列表(SQL 层 ORDER BY + LIMIT/OFFSET + COUNT)。

        替代「全量查出来再 Python 切片」:任务表只增不减,全量加载迟早拖慢列表页。
        bu 非空则按业务单元过滤;keyword 非空则按文件名模糊匹配;mode 非空则按评测模式精确过滤。
        返回 (当前页任务, 总数)。
        """
        from sqlalchemy import func
        conds = [EvalTask.bu == bu] if bu else []
        if keyword:
            conds.append(EvalTask.filename.ilike(f"%{keyword}%"))
        if mode:
            conds.append(EvalTask.mode == mode)
        total = int(self.session.execute(
            select(func.count()).select_from(EvalTask).where(*conds)
        ).scalar() or 0)
        rows = self.session.execute(
            select(EvalTask).where(*conds)
            .order_by(EvalTask.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).scalars().all()
        return [_task_to_dict(t) for t in rows], total

    # ── 多 POD 抢占式调度 ─────────────────────────────────────────────────────

    def claim_next_task(self, worker_id: str) -> dict | None:
        """抢占下一个待跑任务(原子):取最早的 pending 行,FOR UPDATE SKIP LOCKED 锁定,
        置 running + claimed_by/claimed_at/heartbeat,返回该任务。无可抢返回 None。

        SKIP LOCKED 保证多 POD 并发抢占时各拿不同行、互不阻塞;同一行只会被一个 POD 抢到。
        """
        ts = _now()
        row = self.session.execute(
            select(EvalTask)
            .where(EvalTask.status == "pending")
            .order_by(EvalTask.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalars().first()
        if row is None:
            return None
        row.status = "running"
        row.claimed_by = worker_id
        row.claimed_at = ts
        row.heartbeat_at = ts
        row.started_at = ts   # 真正开跑时间：排队等待不计入，一眼看清单次评测耗时
        row.updated_at = ts
        row.updated_by = worker_id
        row.error = None
        self.session.flush()
        return _task_to_dict(row, full=True)

    def heartbeat(self, task_id: str, worker_id: str) -> bool:
        """运行中续约心跳。仅当任务仍是本 worker 持有的 running 时才续(防误续被回收后
        被别的 POD 接管的任务)。返回是否续上。"""
        n = self.session.query(EvalTask).filter(
            EvalTask.task_id == task_id,
            EvalTask.status == "running",
            EvalTask.claimed_by == worker_id,
        ).update({"heartbeat_at": _now()})
        return bool(n)

    def reclaim_stale(self, stale_before: datetime) -> int:
        """回收僵尸任务:running 但心跳早于 stale_before(持有它的 POD 已死)→ 退回
        pending,等待重新抢占续跑。返回回收条数。

        heartbeat_at IS NULL 的 running 也算僵尸:要么是加心跳列之前的历史任务(进程
        重启后会一直卡 running、谁都抢不到),要么是抢占后还没写第一次心跳就崩了——
        两种都没有活着的 worker,必须回收。注意 SQL 里 NULL < x 结果是 NULL(非 true),
        不显式 OR IS NULL 就会漏掉这些行(这正是「重启后旧任务不再续跑」的根因)。"""
        from sqlalchemy import or_
        n = self.session.query(EvalTask).filter(
            EvalTask.status == "running",
            or_(EvalTask.heartbeat_at.is_(None), EvalTask.heartbeat_at < stale_before),
        ).update({
            "status": "pending", "claimed_by": None,
            "stage": "", "updated_at": _now(),
            "error": "worker 心跳超时,已回收重跑",
        }, synchronize_session=False)
        return n

    def requeue_idle(self) -> int:
        """把「确定没在跑」的非终态任务(paused/interrupted)退回 pending 供重抢。

        关键:不碰 running——多 POD 下别的 POD 可能正跑着 running 任务,无条件退回会
        打断它。running 的存活与否一律交给 reclaim_stale 按心跳判定。返回条数。
        """
        n = self.session.query(EvalTask).filter(
            EvalTask.status.in_(("paused", "interrupted")),
        ).update({
            "status": "pending", "claimed_by": None,
            "stage": "", "updated_at": _now(),
        }, synchronize_session=False)
        return n

    def delete_task(self, task_id: str) -> bool:
        """硬删任务主记录 + 逐条结果 + 人工复核。返回是否删到了主记录。"""
        self.session.query(EvalTaskRow).filter(EvalTaskRow.task_id == task_id).delete()
        self.session.query(EvalReview).filter(EvalReview.task_id == task_id).delete()
        n = self.session.query(EvalTask).filter(EvalTask.task_id == task_id).delete()
        return bool(n)

    def clear_rows(self, task_id: str) -> None:
        """清空某任务的逐条结果 + 人工复核（重测前调，让评测从头跑）。

        重测后 AI 判定会变，旧复核针对的是旧结果，留着会张冠李戴，一并清掉。
        """
        self.session.query(EvalTaskRow).filter(EvalTaskRow.task_id == task_id).delete()
        self.session.query(EvalReview).filter(EvalReview.task_id == task_id).delete()

    # ── 逐条结果 ──────────────────────────────────────────────────────────────

    def save_rows(self, task_id: str, rows: list[dict], created_by: str = "system") -> None:
        """批量 upsert 逐条结果（断点续跑的依据）。

        双写：拆出平铺列（明细过滤/洞察聚合用）+ judge/context/gold 三个 JSON 列，
        同时保留 row_json 整体快照（旧行兜底 + 过渡期回退安全）。
        """
        if not rows:
            return
        ts = _now()
        payload = [
            {
                "task_id": task_id, "row_index": r["row_index"],
                "session": r.get("session"), "turn": r.get("turn"),
                "question": r.get("question"), "ask_time": r.get("ask_time", ""),
                "dispatched_bu": r.get("dispatched_bu", ""),
                "j_intent": r.get("j_intent"), "j_dispatch": r.get("j_dispatch"),
                "j_resolved": r.get("j_resolved"),
                "judge_json": _clean_json(r.get("judge")),
                "context_json": _clean_json(r.get("context")),
                "gold_json": _clean_json(r.get("gold")),
                "row_json": _clean_json(r),
                "created_at": ts, "created_by": created_by,
            }
            for r in rows
        ]
        stmt = pg_insert(EvalTaskRow).values(payload)
        # 重跑覆盖：所有拆出列 + row_json 都要同步更新，否则平铺列与 row_json 不一致
        ex = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["task_id", "row_index"],
            set_={
                "session": ex.session, "turn": ex.turn, "question": ex.question,
                "ask_time": ex.ask_time, "dispatched_bu": ex.dispatched_bu,
                "j_intent": ex.j_intent, "j_dispatch": ex.j_dispatch, "j_resolved": ex.j_resolved,
                "judge_json": ex.judge_json, "context_json": ex.context_json,
                "gold_json": ex.gold_json, "row_json": ex.row_json,
            },
        )
        self.session.execute(stmt)

    def done_row_indices(self, task_id: str) -> set[int]:
        """已落盘的 row_index 集合，用于跳过、断点续跑。"""
        rows = self.session.execute(
            select(EvalTaskRow.row_index).where(EvalTaskRow.task_id == task_id)
        ).scalars().all()
        return set(rows)

    def _row_filters(self, task_id: str, f: dict):
        """构造逐条结果的过滤条件。f 支持：
        q(问题关键字, 模糊) / intent(业务分类, 精确) / dispatched_bu(分发BU, 模糊) /
        j_dispatch(分发判定 是/否, 精确) / j_resolved(是否解决 是/否, 精确)。

        新行读平铺列（走索引），旧行平铺列可能为空 → COALESCE 兜底 row_json。
        过滤已按 task_id 缩到单任务范围，COALESCE 让索引失效在此不构成问题。
        """
        from sqlalchemy import func
        conds = [EvalTaskRow.task_id == task_id]
        rj = EvalTaskRow.row_json

        def col(flat, key):
            return func.coalesce(flat, rj[key].astext)

        if f.get("q"):
            conds.append(col(EvalTaskRow.question, "question").ilike(f"%{f['q']}%"))
        if f.get("intent"):
            conds.append(col(EvalTaskRow.j_intent, "j_intent") == f["intent"])
        if f.get("dispatched_bu"):
            conds.append(col(EvalTaskRow.dispatched_bu, "dispatched_bu").ilike(f"%{f['dispatched_bu']}%"))
        if f.get("j_dispatch"):
            conds.append(col(EvalTaskRow.j_dispatch, "j_dispatch") == f["j_dispatch"])
        if f.get("j_resolved"):
            conds.append(col(EvalTaskRow.j_resolved, "j_resolved") == f["j_resolved"])
        return conds

    def load_rows_filtered(self, task_id: str, page: int, page_size: int, filters: dict) -> list[dict]:
        """分页 + 多字段过滤读逐条结果。"""
        offset = (page - 1) * page_size
        rows = self.session.execute(
            select(EvalTaskRow.row_json)
            .where(*self._row_filters(task_id, filters))
            .order_by(EvalTaskRow.row_index)
            .offset(offset).limit(page_size)
        ).scalars().all()
        return list(rows)

    def count_rows_filtered(self, task_id: str, filters: dict) -> int:
        from sqlalchemy import func
        return int(self.session.execute(
            select(func.count()).select_from(EvalTaskRow)
            .where(*self._row_filters(task_id, filters))
        ).scalar() or 0)

    def load_rows_by_indices(self, task_id: str, indices: list[int]) -> dict[int, dict]:
        """按 row_index 集合批量取 row_json，返回 {row_index: row_json}。

        复核指标重算用：只取「被复核的那几条」的 AI 原判，集合很小，1 次 IN 查询，
        不扫全表。空集合直接返回空 dict（不发查询）。
        """
        if not indices:
            return {}
        rows = self.session.execute(
            select(EvalTaskRow.row_index, EvalTaskRow.row_json)
            .where(EvalTaskRow.task_id == task_id, EvalTaskRow.row_index.in_(indices))
        ).all()
        return {int(idx): rj for idx, rj in rows}

    def load_rows_after(self, task_id: str, after_index: int, limit: int) -> list[tuple[int, dict]]:
        """游标分页：取 row_index > after_index 的下一批，返回 [(row_index, row_json)]。

        导出迭代专用。相比 OFFSET 分页（导出到第 N 页要先扫过前 N×size 行再丢弃，
        整体 O(N²)），游标分页每批都走 (task_id, row_index) 唯一索引定位，整体 O(N)，
        百万级也不会越翻越慢。返回 row_index 供调用方推进游标。
        """
        rows = self.session.execute(
            select(EvalTaskRow.row_index, EvalTaskRow.row_json)
            .where(EvalTaskRow.task_id == task_id, EvalTaskRow.row_index > after_index)
            .order_by(EvalTaskRow.row_index)
            .limit(limit)
        ).all()
        return [(int(idx), rj) for idx, rj in rows]

    def load_review_rows(self, task_id: str, limit: int = 500) -> list[dict]:
        """读「待人工复核」的行（needs_human_review 且尚未被复核），上限 limit。

        排除已在 t_eval_review 有记录的行——它们已人工确认、summary 需复核数也已扣除，
        不应再出现在「需复核」队列(否则复核完还显示、且与指标口径不一致)。
        """
        reviewed = (
            select(EvalReview.row_index).where(EvalReview.task_id == task_id).scalar_subquery()
        )
        rows = self.session.execute(
            select(EvalTaskRow.row_json)
            .where(
                EvalTaskRow.task_id == task_id,
                EvalTaskRow.row_json["judge"]["needs_human_review"].as_boolean().is_(True),
                EvalTaskRow.row_index.notin_(reviewed),
            )
            .order_by(EvalTaskRow.row_index)
            .limit(limit)
        ).scalars().all()
        return list(rows)

    def rerun_subset_indices(self, task_id: str, flag: str) -> list[int]:
        """按筛选取待重跑的 row_index(排除已复核行——人工结论优先,不被自动覆盖)。

        阶段一支持 flag='review'(待人工复核)。返回升序 row_index 列表。
        """
        reviewed = (
            select(EvalReview.row_index).where(EvalReview.task_id == task_id).scalar_subquery()
        )
        conds = [EvalTaskRow.task_id == task_id, EvalTaskRow.row_index.notin_(reviewed)]
        if flag == "review":
            conds.append(
                EvalTaskRow.row_json["judge"]["needs_human_review"].as_boolean().is_(True)
            )
        else:
            raise ValueError(f"暂不支持的重跑筛选: {flag}")
        rows = self.session.execute(
            select(EvalTaskRow.row_index).where(*conds).order_by(EvalTaskRow.row_index)
        ).scalars().all()
        return [int(i) for i in rows]

    def iter_all_row_jsons(self, task_id: str, batch_size: int = 1000):
        """分批读回该任务全部 row_json(按 row_index 升序,keyset),供全量重算 summary。"""
        after = -1
        while True:
            batch = self.session.execute(
                select(EvalTaskRow.row_index, EvalTaskRow.row_json)
                .where(EvalTaskRow.task_id == task_id, EvalTaskRow.row_index > after)
                .order_by(EvalTaskRow.row_index)
                .limit(batch_size)
            ).all()
            if not batch:
                break
            yield [rj for _idx, rj in batch]
            after = int(batch[-1][0])
            if len(batch) < batch_size:
                break

    # ── 聚合结果 ──────────────────────────────────────────────────────────────

    def save_result(self, task_id: str, result: dict, updated_by: str = "system") -> None:
        """落盘聚合结果（不含逐条 rows——rows 在 t_eval_task_row，前端分页查）。

        disagreements 是有限代表样本（上限见 evaluator._MAX_DISAGREEMENTS），随聚合
        结果入库供报表/导出；全量逐条不入 result_json，避免百万级把单行 JSONB 撑爆。
        """
        slim = {k: v for k, v in result.items() if k != "rows"}
        self.update_task(task_id, updated_by=updated_by, result_json=_clean_json(slim))

    def load_result(self, task_id: str) -> dict | None:
        """读回聚合结果。不再附带全量 rows（百万级 OOM）；逐条走 load_rows_paged。"""
        t = self.get_task(task_id)
        if not t or not t.get("result_json"):
            return None
        return dict(t["result_json"])

    # ── 问题洞察聚合（跨任务，按 BU；全部走 PG 层 GROUP BY，避免 N+1）──────────────

    def _bu_row_query(self, bu: str, intent: str = "", start: str = "", end: str = ""):
        """构造 t_eval_task_row JOIN t_eval_task 按 bu 过滤的基础查询条件（供聚合复用）。

        查平铺列（question/j_intent/ask_time）走原生索引；旧行这三列已由迁移脚本回填。
        intent 非空按业务分类过滤；start/end 非空按提问日期（ask_time 前 10 位）过滤。
        """
        from sqlalchemy import func
        q_ask_date = func.substr(EvalTaskRow.ask_time, 1, 10)
        conds = [EvalTask.bu == bu]
        if intent:
            conds.append(EvalTaskRow.j_intent == intent)
        if start:
            conds.append(q_ask_date >= start)
        if end:
            conds.append(q_ask_date <= end)
        return conds, q_ask_date

    def agg_top_questions(self, bu: str, intent: str = "", start: str = "",
                          end: str = "", limit: int = 100) -> tuple[list[dict], int]:
        """按问题原文聚合高频问榜单（不做相似归一）。返回 (榜单, 该 BU 匹配总条数)。"""
        from sqlalchemy import func
        conds, _ = self._bu_row_query(bu, intent, start, end)
        q_text = EvalTaskRow.question
        q_intent = EvalTaskRow.j_intent
        base = select(q_text.label("question"), q_intent.label("intent"),
                      func.count().label("cnt")).select_from(EvalTaskRow).join(
            EvalTask, EvalTaskRow.task_id == EvalTask.task_id).where(*conds)
        total = int(self.session.execute(
            select(func.count()).select_from(EvalTaskRow).join(
                EvalTask, EvalTaskRow.task_id == EvalTask.task_id).where(*conds)
        ).scalar() or 0)
        rows = self.session.execute(
            base.group_by(q_text, q_intent).order_by(func.count().desc()).limit(limit)
        ).all()
        items = [{"question": r.question or "", "intent": r.intent or "",
                  "count": int(r.cnt)} for r in rows]
        return items, total

    def agg_daily_counts(self, bu: str, intent: str = "", start: str = "",
                         end: str = "") -> list[dict]:
        """按提问日期（ask_time 前 10 位）聚合每日问题量。忽略 ask_time 为空的行。"""
        from sqlalchemy import func
        conds, q_ask_date = self._bu_row_query(bu, intent, start, end)
        conds.append(EvalTaskRow.ask_time != "")
        conds.append(EvalTaskRow.ask_time.isnot(None))
        rows = self.session.execute(
            select(q_ask_date.label("d"), func.count().label("cnt"))
            .select_from(EvalTaskRow).join(
                EvalTask, EvalTaskRow.task_id == EvalTask.task_id).where(*conds)
            .group_by(q_ask_date).order_by(q_ask_date)
        ).all()
        return [{"date": r.d, "count": int(r.cnt)} for r in rows if r.d]

    def agg_keyword_source(self, bu: str, intent: str = "",
                           limit_rows: int = 20000) -> tuple[list[tuple[str, str]], bool]:
        """取问题文本 + j_intent 两列供 engine 做分词提词。返回 (行列表, 是否被截断)。

        limit_rows 控内存：大 BU 只取前 N 行做关键词提炼，够代表性且不 OOM。
        """
        conds, _ = self._bu_row_query(bu, intent)
        q_text = EvalTaskRow.question
        q_intent = EvalTaskRow.j_intent
        rows = self.session.execute(
            select(q_text, q_intent).select_from(EvalTaskRow).join(
                EvalTask, EvalTaskRow.task_id == EvalTask.task_id).where(*conds)
            .limit(limit_rows + 1)
        ).all()
        truncated = len(rows) > limit_rows
        data = [(r[0] or "", r[1] or "") for r in rows[:limit_rows]]
        return data, truncated


def _prompt_to_dict(p: EvalPrompt) -> dict[str, Any]:
    return {
        "id": p.id, "bu": p.bu, "name": p.name,
        "content": p.content, "description": p.description,
        "updated_at": _iso(p.updated_at), "updated_by": p.updated_by,
    }


class EvalPromptRepository:
    """提示词持久化层。(bu, name) 唯一；库中无记录时由加载层回退读文件。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, bu: str, name: str) -> dict | None:
        p = self.session.query(EvalPrompt).filter(
            EvalPrompt.bu == bu, EvalPrompt.name == name
        ).first()
        return _prompt_to_dict(p) if p else None

    def list_all(self) -> list[dict]:
        rows = self.session.execute(
            select(EvalPrompt).order_by(EvalPrompt.bu, EvalPrompt.name)
        ).scalars().all()
        return [_prompt_to_dict(p) for p in rows]

    def upsert(self, bu: str, name: str, content: str,
               description: str | None = None, updated_by: str = "system") -> dict:
        """按 (bu, name) upsert。description 为 None 时不覆盖已有说明。"""
        ts = _now()
        values = {
            "bu": bu, "name": name, "content": content,
            "description": description or "",
            "created_at": ts, "created_by": updated_by,
            "updated_at": ts, "updated_by": updated_by,
        }
        set_ = {"content": content, "updated_at": ts, "updated_by": updated_by}
        if description is not None:
            set_["description"] = description
        stmt = pg_insert(EvalPrompt).values(**values).on_conflict_do_update(
            index_elements=["bu", "name"], set_=set_,
        )
        self.session.execute(stmt)
        return self.get(bu, name)

    def delete(self, bu: str, name: str) -> bool:
        """删除一条（回退到文件默认）。返回是否真的删了。"""
        n = self.session.query(EvalPrompt).filter(
            EvalPrompt.bu == bu, EvalPrompt.name == name
        ).delete()
        return bool(n)


def _category_to_dict(c: EvalCategory) -> dict[str, Any]:
    return {
        "id": c.id, "bu": c.bu, "name": c.name,
        "definition": c.definition, "sort_order": c.sort_order,
        "updated_at": _iso(c.updated_at), "updated_by": c.updated_by,
    }


class EvalCategoryRepository:
    """业务分类持久化层。(bu, name) 唯一；库中某 BU 无记录时由加载层回退读文件。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_bu(self, bu: str) -> list[dict]:
        rows = self.session.execute(
            select(EvalCategory).where(EvalCategory.bu == bu)
            .order_by(EvalCategory.sort_order, EvalCategory.id)
        ).scalars().all()
        return [_category_to_dict(c) for c in rows]

    def count_by_bu(self, bu: str) -> int:
        from sqlalchemy import func
        return int(self.session.execute(
            select(func.count()).select_from(EvalCategory).where(EvalCategory.bu == bu)
        ).scalar() or 0)

    def get(self, cat_id: int) -> dict | None:
        c = self.session.get(EvalCategory, cat_id)
        return _category_to_dict(c) if c else None

    def create(self, bu: str, name: str, definition: str,
               sort_order: int = 0, created_by: str = "system") -> dict:
        ts = _now()
        c = EvalCategory(
            bu=bu, name=name, definition=definition, sort_order=sort_order,
            created_at=ts, created_by=created_by, updated_at=ts, updated_by=created_by,
        )
        self.session.add(c)
        self.session.flush()
        return _category_to_dict(c)

    def update(self, cat_id: int, name: str | None = None, definition: str | None = None,
               sort_order: int | None = None, updated_by: str = "system") -> dict | None:
        c = self.session.get(EvalCategory, cat_id)
        if not c:
            return None
        if name is not None:
            c.name = name
        if definition is not None:
            c.definition = definition
        if sort_order is not None:
            c.sort_order = sort_order
        c.updated_at = _now()
        c.updated_by = updated_by
        self.session.flush()
        return _category_to_dict(c)

    def delete(self, cat_id: int) -> bool:
        n = self.session.query(EvalCategory).filter(EvalCategory.id == cat_id).delete()
        return bool(n)

    def bulk_seed(self, bu: str, items: list[dict], created_by: str = "system") -> None:
        """把文件出厂分类写入库（库中该 BU 为空时首次落库）。

        ON CONFLICT DO NOTHING 保证幂等:多 POD 同时启动可能都看到「库为空」而并发
        seed,靠 (bu, name) 唯一约束 + 忽略冲突,避免第二个 POD 撞唯一约束报错、启动失败。
        """
        if not items:
            return
        ts = _now()
        stmt = pg_insert(EvalCategory).values([
            {"bu": bu, "name": it["name"], "definition": it["definition"],
             "sort_order": i, "created_at": ts, "created_by": created_by,
             "updated_at": ts, "updated_by": created_by}
            for i, it in enumerate(items)
        ]).on_conflict_do_nothing(index_elements=["bu", "name"])
        self.session.execute(stmt)


def _activity_to_dict(a: EvalActivityQuestion) -> dict[str, Any]:
    return {
        "id": a.id, "bu": a.bu, "question": a.question,
        "activity_name": a.activity_name or "", "note": a.note,
        "updated_at": _iso(a.updated_at), "updated_by": a.updated_by,
    }


class EvalActivityRepository:
    """活动标问持久化层。(bu, question) 唯一；与客户问题精确相等即命中、整条跳过评测。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_bu(self, bu: str) -> list[dict]:
        rows = self.session.execute(
            select(EvalActivityQuestion).where(EvalActivityQuestion.bu == bu)
            .order_by(EvalActivityQuestion.id)
        ).scalars().all()
        return [_activity_to_dict(a) for a in rows]

    def list_questions(self, bu: str) -> list[tuple[str, str]]:
        """取 (question, activity_name) 列表，供评测加载活动标问映射（避免拉全字段）。"""
        rows = self.session.execute(
            select(EvalActivityQuestion.question, EvalActivityQuestion.activity_name)
            .where(EvalActivityQuestion.bu == bu)
        ).all()
        return [(q, a) for q, a in rows]

    def create(self, bu: str, question: str, note: str = "", activity_name: str = "",
               created_by: str = "system") -> dict:
        ts = _now()
        act = (activity_name or "").strip() or question   # 活动名空时兜底用 question
        stmt = pg_insert(EvalActivityQuestion).values(
            bu=bu, question=question, activity_name=act, note=note,
            created_at=ts, created_by=created_by, updated_at=ts, updated_by=created_by,
        ).on_conflict_do_update(
            index_elements=["bu", "question"],
            set_={"activity_name": act, "note": note, "updated_at": ts, "updated_by": created_by},
        )
        self.session.execute(stmt)
        a = self.session.execute(
            select(EvalActivityQuestion).where(
                EvalActivityQuestion.bu == bu, EvalActivityQuestion.question == question
            )
        ).scalars().first()
        return _activity_to_dict(a)

    def create_many(self, bu: str, items: list[dict], created_by: str = "system") -> list[dict]:
        """批量新增（同一活动多条标问一次录入）。逐条 upsert，(bu, question) 冲突则更新。

        items 每项 {question, activity_name?, note?}；question 已去空、调用方保证非空且去重。
        """
        ts = _now()
        for it in items:
            q = it["question"]
            act = (it.get("activity_name") or "").strip() or q
            self.session.execute(
                pg_insert(EvalActivityQuestion).values(
                    bu=bu, question=q, activity_name=act, note=it.get("note", ""),
                    created_at=ts, created_by=created_by, updated_at=ts, updated_by=created_by,
                ).on_conflict_do_update(
                    index_elements=["bu", "question"],
                    set_={"activity_name": act, "note": it.get("note", ""),
                          "updated_at": ts, "updated_by": created_by},
                )
            )
        questions = [it["question"] for it in items]
        rows = self.session.execute(
            select(EvalActivityQuestion).where(
                EvalActivityQuestion.bu == bu, EvalActivityQuestion.question.in_(questions)
            )
        ).scalars().all()
        return [_activity_to_dict(a) for a in rows]

    def update(self, act_id: int, question: str, activity_name: str = "",
               note: str = "", updated_by: str = "system") -> dict | None:
        """按 id 更新单条。question 可改，改后若与同 BU 其它行重名则视为冲突返回 None。"""
        a = self.session.get(EvalActivityQuestion, act_id)
        if a is None:
            return None
        if question != a.question:
            dup = self.session.execute(
                select(EvalActivityQuestion.id).where(
                    EvalActivityQuestion.bu == a.bu,
                    EvalActivityQuestion.question == question,
                    EvalActivityQuestion.id != act_id,
                )
            ).scalars().first()
            if dup:
                return None
        a.question = question
        a.activity_name = (activity_name or "").strip() or question
        a.note = note
        a.updated_at = _now()
        a.updated_by = updated_by
        self.session.flush()
        return _activity_to_dict(a)

    def delete(self, act_id: int) -> bool:
        n = self.session.query(EvalActivityQuestion).filter(
            EvalActivityQuestion.id == act_id
        ).delete()
        return bool(n)


def _review_to_dict(r: EvalReview) -> dict[str, Any]:
    return {
        "task_id": r.task_id, "row_index": r.row_index,
        "reviewed_dispatch": r.reviewed_dispatch, "reviewed_resolved": r.reviewed_resolved,
        "reviewed_intent": r.reviewed_intent, "comment": r.comment,
        "reviewer": r.reviewer, "updated_at": _iso(r.updated_at),
    }


class EvalReviewRepository:
    """人工复核覆盖持久化层。(task_id, row_index) 唯一，同一条可反复复核（upsert）。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, task_id: str, row_index: int, *, reviewed_dispatch: str = "",
               reviewed_resolved: str = "", reviewed_intent: str = "",
               comment: str = "", reviewer: str = "system") -> dict:
        ts = _now()
        stmt = pg_insert(EvalReview).values(
            task_id=task_id, row_index=row_index,
            reviewed_dispatch=reviewed_dispatch, reviewed_resolved=reviewed_resolved,
            reviewed_intent=reviewed_intent, comment=comment, reviewer=reviewer,
            created_at=ts, created_by=reviewer, updated_at=ts, updated_by=reviewer,
        ).on_conflict_do_update(
            index_elements=["task_id", "row_index"],
            set_={
                "reviewed_dispatch": reviewed_dispatch, "reviewed_resolved": reviewed_resolved,
                "reviewed_intent": reviewed_intent, "comment": comment, "reviewer": reviewer,
                "updated_at": ts, "updated_by": reviewer,
            },
        )
        self.session.execute(stmt)
        return self.get(task_id, row_index)

    def get(self, task_id: str, row_index: int) -> dict | None:
        r = self.session.execute(
            select(EvalReview).where(
                EvalReview.task_id == task_id, EvalReview.row_index == row_index
            )
        ).scalars().first()
        return _review_to_dict(r) if r else None

    def list_by_task(self, task_id: str) -> list[dict]:
        """某任务的全部复核（用于指标重算 + 明细叠加）。复核是少量子集，全量返回无碍。"""
        rows = self.session.execute(
            select(EvalReview).where(EvalReview.task_id == task_id)
        ).scalars().all()
        return [_review_to_dict(r) for r in rows]

    def delete(self, task_id: str, row_index: int) -> bool:
        """撤销复核（删除覆盖，该行恢复用 AI 判定）。"""
        n = self.session.query(EvalReview).filter(
            EvalReview.task_id == task_id, EvalReview.row_index == row_index
        ).delete()
        return bool(n)

def _rule_to_dict(r: EvalRule) -> dict[str, Any]:
    return {
        "id": r.id, "bu": r.bu, "name": r.name,
        "questions": r.questions or [], "answers": r.answers or [],
        "judge_json": r.judge_json,
        "note": r.note, "updated_at": _iso(r.updated_at), "updated_by": r.updated_by,
    }


class EvalRuleRepository:
    """规则短路持久化层（规则集）。(bu, name) 唯一；命中即用写死 judge 结果免 LLM。

    一个规则 = name + 触发问题集合 questions + 期望答案集合 answers + judge。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_bu(self, bu: str) -> list[dict]:
        rows = self.session.execute(
            select(EvalRule).where(EvalRule.bu == bu).order_by(EvalRule.id)
        ).scalars().all()
        return [_rule_to_dict(r) for r in rows]

    def list_for_match(self, bu: str) -> list[dict]:
        """取匹配所需字段（name/questions/answers/judge_json），供评测加载规则集合。"""
        rows = self.session.execute(
            select(EvalRule.name, EvalRule.questions, EvalRule.answers, EvalRule.judge_json)
            .where(EvalRule.bu == bu)
        ).all()
        return [{"name": n, "questions": qs or [], "answers": ans or [], "judge_json": jj}
                for n, qs, ans, jj in rows]

    def upsert(self, bu: str, name: str, questions: list[str], answers: list[str],
               judge_json: dict, note: str = "", updated_by: str = "system") -> dict:
        ts = _now()
        # 去空去重（保序），并回写旧列首元素作历史兼容
        qs = list(dict.fromkeys(q.strip() for q in questions if q and q.strip()))
        ans = list(dict.fromkeys(a.strip() for a in answers if a and a.strip()))
        first_q = qs[0] if qs else ""
        first_a = ans[0] if ans else ""
        vals = dict(
            bu=bu, name=name, questions=qs, answers=ans,
            question=first_q, expected_answer=first_a,
            judge_json=_clean_json(judge_json), note=note,
        )
        stmt = pg_insert(EvalRule).values(
            **vals, created_at=ts, created_by=updated_by, updated_at=ts, updated_by=updated_by,
        ).on_conflict_do_update(
            index_elements=["bu", "name"],
            set_={**vals, "updated_at": ts, "updated_by": updated_by},
        )
        self.session.execute(stmt)
        r = self.session.execute(
            select(EvalRule).where(EvalRule.bu == bu, EvalRule.name == name)
        ).scalars().first()
        return _rule_to_dict(r)

    def delete(self, rule_id: int) -> bool:
        n = self.session.query(EvalRule).filter(EvalRule.id == rule_id).delete()
        return bool(n)
