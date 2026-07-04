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
        """批量 upsert 逐条结果（断点续跑的依据）。"""
        if not rows:
            return
        ts = _now()
        payload = [
            {"task_id": task_id, "row_index": r["row_index"], "row_json": _clean_json(r),
             "created_at": ts, "created_by": created_by}
            for r in rows
        ]
        stmt = pg_insert(EvalTaskRow).values(payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=["task_id", "row_index"],
            set_={"row_json": stmt.excluded.row_json},
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
        """
        conds = [EvalTaskRow.task_id == task_id]
        rj = EvalTaskRow.row_json
        if f.get("q"):
            conds.append(rj["question"].astext.ilike(f"%{f['q']}%"))
        if f.get("intent"):
            conds.append(rj["j_intent"].astext == f["intent"])
        if f.get("dispatched_bu"):
            conds.append(rj["dispatched_bu"].astext.ilike(f"%{f['dispatched_bu']}%"))
        if f.get("j_dispatch"):
            conds.append(rj["j_dispatch"].astext == f["j_dispatch"])
        if f.get("j_resolved"):
            conds.append(rj["j_resolved"].astext == f["j_resolved"])
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
        "id": a.id, "bu": a.bu, "question": a.question, "note": a.note,
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

    def list_questions(self, bu: str) -> list[str]:
        """只取 question 文本列表，供评测加载活动标问集合（避免拉全字段）。"""
        rows = self.session.execute(
            select(EvalActivityQuestion.question).where(EvalActivityQuestion.bu == bu)
        ).scalars().all()
        return list(rows)

    def create(self, bu: str, question: str, note: str = "", created_by: str = "system") -> dict:
        ts = _now()
        stmt = pg_insert(EvalActivityQuestion).values(
            bu=bu, question=question, note=note,
            created_at=ts, created_by=created_by, updated_at=ts, updated_by=created_by,
        ).on_conflict_do_update(
            index_elements=["bu", "question"],
            set_={"note": note, "updated_at": ts, "updated_by": created_by},
        )
        self.session.execute(stmt)
        a = self.session.execute(
            select(EvalActivityQuestion).where(
                EvalActivityQuestion.bu == bu, EvalActivityQuestion.question == question
            )
        ).scalars().first()
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

    def delete_all(self, task_id: str) -> None:
        """删任务时清理其复核（连带删除）。"""
        self.session.query(EvalReview).filter(EvalReview.task_id == task_id).delete()


def _rule_to_dict(r: EvalRule) -> dict[str, Any]:
    return {
        "id": r.id, "bu": r.bu, "question": r.question,
        "expected_answer": r.expected_answer, "judge_json": r.judge_json,
        "note": r.note, "updated_at": _iso(r.updated_at), "updated_by": r.updated_by,
    }


class EvalRuleRepository:
    """规则短路持久化层。(bu, question) 唯一；命中即用写死 judge 结果免 LLM。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_bu(self, bu: str) -> list[dict]:
        rows = self.session.execute(
            select(EvalRule).where(EvalRule.bu == bu).order_by(EvalRule.id)
        ).scalars().all()
        return [_rule_to_dict(r) for r in rows]

    def list_for_match(self, bu: str) -> list[dict]:
        """取匹配所需字段（question/expected_answer/judge_json），供评测加载规则集合。"""
        rows = self.session.execute(
            select(EvalRule.question, EvalRule.expected_answer, EvalRule.judge_json)
            .where(EvalRule.bu == bu)
        ).all()
        return [{"question": q, "expected_answer": ea, "judge_json": jj} for q, ea, jj in rows]

    def upsert(self, bu: str, question: str, expected_answer: str, judge_json: dict,
               note: str = "", updated_by: str = "system") -> dict:
        ts = _now()
        stmt = pg_insert(EvalRule).values(
            bu=bu, question=question, expected_answer=expected_answer,
            judge_json=_clean_json(judge_json), note=note,
            created_at=ts, created_by=updated_by, updated_at=ts, updated_by=updated_by,
        ).on_conflict_do_update(
            index_elements=["bu", "question"],
            set_={"expected_answer": expected_answer, "judge_json": _clean_json(judge_json),
                  "note": note, "updated_at": ts, "updated_by": updated_by},
        )
        self.session.execute(stmt)
        r = self.session.execute(
            select(EvalRule).where(EvalRule.bu == bu, EvalRule.question == question)
        ).scalars().first()
        return _rule_to_dict(r)

    def delete(self, rule_id: int) -> bool:
        n = self.session.query(EvalRule).filter(EvalRule.id == rule_id).delete()
        return bool(n)
