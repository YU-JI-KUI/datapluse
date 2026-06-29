"""Eval repository — t_eval_task / t_eval_task_row

AI 对话评测的持久化层（独立于标注数据集）。逐条结果落盘后，任务跑一半中断
可断点续跑（只补未完成的行）。JSON 列用 JSONB（可查询/索引）。

由 ark-dialog-eval 的 services/store.py 平移而来，对外函数语义保持等价，
适配 datapulse 规范：id BIGSERIAL 主键、TIMESTAMP 审计字段、ISO 时间出参。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from datapulse.modules.eval.entities import EvalCategory, EvalPrompt, EvalTask, EvalTaskRow

_SHANGHAI = ZoneInfo("Asia/Shanghai")


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

    def list_tasks(self) -> list[dict]:
        rows = self.session.execute(
            select(EvalTask).order_by(EvalTask.created_at.desc())
        ).scalars().all()
        return [_task_to_dict(t) for t in rows]

    def find_unfinished(self) -> list[dict]:
        """找未到终态(done/failed)的任务，供启动时自动恢复。返回 [{task_id, status, created_by}]。"""
        rows = self.session.execute(
            select(EvalTask.task_id, EvalTask.status, EvalTask.created_by)
            .where(EvalTask.status.in_(("running", "paused", "interrupted", "pending")))
            .order_by(EvalTask.created_at)
        ).all()
        return [{"task_id": tid, "status": st, "created_by": cb} for tid, st, cb in rows]

    def delete_task(self, task_id: str) -> bool:
        """硬删任务主记录 + 逐条结果。返回是否删到了主记录。"""
        self.session.query(EvalTaskRow).filter(EvalTaskRow.task_id == task_id).delete()
        n = self.session.query(EvalTask).filter(EvalTask.task_id == task_id).delete()
        return bool(n)

    def clear_rows(self, task_id: str) -> None:
        """清空某任务的逐条结果（重测前调，让评测从头跑）。"""
        self.session.query(EvalTaskRow).filter(EvalTaskRow.task_id == task_id).delete()

    # ── 逐条结果 ──────────────────────────────────────────────────────────────

    def save_rows(self, task_id: str, rows: list[dict], created_by: str = "system") -> None:
        """批量 upsert 逐条结果（断点续跑的依据）。"""
        if not rows:
            return
        ts = _now()
        payload = [
            {"task_id": task_id, "row_index": r["row_index"], "row_json": r,
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

    def load_rows(self, task_id: str) -> list[dict]:
        """读回所有逐条结果（按 row_index 排序）。仅用于小数据量场景。"""
        rows = self.session.execute(
            select(EvalTaskRow.row_json)
            .where(EvalTaskRow.task_id == task_id)
            .order_by(EvalTaskRow.row_index)
        ).scalars().all()
        return list(rows)

    def load_rows_paged(self, task_id: str, page: int, page_size: int) -> list[dict]:
        """分页读逐条结果（按 row_index 排序）。百万级下避免一次性全量加载。"""
        offset = (page - 1) * page_size
        rows = self.session.execute(
            select(EvalTaskRow.row_json)
            .where(EvalTaskRow.task_id == task_id)
            .order_by(EvalTaskRow.row_index)
            .offset(offset).limit(page_size)
        ).scalars().all()
        return list(rows)

    def count_rows(self, task_id: str) -> int:
        from sqlalchemy import func
        return int(self.session.execute(
            select(func.count()).select_from(EvalTaskRow).where(EvalTaskRow.task_id == task_id)
        ).scalar() or 0)

    def _row_filters(self, task_id: str, q: str = "", intent: str = ""):
        """构造逐条结果的过滤条件：task_id + 关键字(问题) + 业务分类。"""
        conds = [EvalTaskRow.task_id == task_id]
        if q:
            conds.append(EvalTaskRow.row_json["question"].astext.ilike(f"%{q}%"))
        if intent:
            conds.append(EvalTaskRow.row_json["j_intent"].astext == intent)
        return conds

    def load_rows_filtered(self, task_id: str, page: int, page_size: int,
                           q: str = "", intent: str = "") -> list[dict]:
        """分页 + 关键字(问题)/业务分类过滤读逐条结果。"""
        offset = (page - 1) * page_size
        rows = self.session.execute(
            select(EvalTaskRow.row_json)
            .where(*self._row_filters(task_id, q, intent))
            .order_by(EvalTaskRow.row_index)
            .offset(offset).limit(page_size)
        ).scalars().all()
        return list(rows)

    def count_rows_filtered(self, task_id: str, q: str = "", intent: str = "") -> int:
        from sqlalchemy import func
        return int(self.session.execute(
            select(func.count()).select_from(EvalTaskRow)
            .where(*self._row_filters(task_id, q, intent))
        ).scalar() or 0)

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
        """读「需人工复核」的行（JSONB 过滤），上限 limit。

        需复核是要人工处理的有限子集，与 disagreements 对称只取代表样本，
        百万级下不做全量返回。row_json->'judge'->>'needs_human_review' 为真即命中。
        """
        rows = self.session.execute(
            select(EvalTaskRow.row_json)
            .where(
                EvalTaskRow.task_id == task_id,
                EvalTaskRow.row_json["judge"]["needs_human_review"].as_boolean().is_(True),
            )
            .order_by(EvalTaskRow.row_index)
            .limit(limit)
        ).scalars().all()
        return list(rows)

    # ── 聚合结果 ──────────────────────────────────────────────────────────────

    def save_result(self, task_id: str, result: dict, updated_by: str = "system") -> None:
        """落盘聚合结果（不含逐条 rows——rows 在 t_eval_task_row，前端分页查）。

        disagreements 是有限代表样本（上限见 evaluator._MAX_DISAGREEMENTS），随聚合
        结果入库供报表/导出；全量逐条不入 result_json，避免百万级把单行 JSONB 撑爆。
        """
        slim = {k: v for k, v in result.items() if k != "rows"}
        self.update_task(task_id, updated_by=updated_by, result_json=slim)

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
        """把文件出厂分类一次性写入库（仅当该 BU 库中为空时调，用于首次落库）。"""
        if not items:
            return
        ts = _now()
        self.session.bulk_insert_mappings(EvalCategory, [
            {"bu": bu, "name": it["name"], "definition": it["definition"],
             "sort_order": i, "created_at": ts, "created_by": created_by,
             "updated_at": ts, "updated_by": created_by}
            for i, it in enumerate(items)
        ])
