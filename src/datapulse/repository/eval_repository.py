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

from datapulse.model.entities import EvalTask, EvalTaskRow

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# 任务元数据对外暴露的列（list_tasks 用，不含大字段 result_json）
_TASK_PUBLIC_KEYS = (
    "id", "task_id", "filename", "bu", "status", "stage", "mode",
    "progress_done", "progress_total", "error",
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
        """读回所有逐条结果（按 row_index 排序）。"""
        rows = self.session.execute(
            select(EvalTaskRow.row_json)
            .where(EvalTaskRow.task_id == task_id)
            .order_by(EvalTaskRow.row_index)
        ).scalars().all()
        return list(rows)

    # ── 聚合结果 ──────────────────────────────────────────────────────────────

    def save_result(self, task_id: str, result: dict, updated_by: str = "system") -> None:
        """落盘聚合结果（不含逐条 rows——rows 在 t_eval_task_row）。"""
        slim = {k: v for k, v in result.items() if k not in ("rows", "disagreements")}
        self.update_task(task_id, updated_by=updated_by, result_json=slim)

    def load_result(self, task_id: str) -> dict | None:
        t = self.get_task(task_id)
        if not t or not t.get("result_json"):
            return None
        result = dict(t["result_json"])
        rows = self.load_rows(task_id)
        result["rows"] = rows
        result["disagreements"] = [r for r in rows if r.get("is_disagreement")]
        return result
