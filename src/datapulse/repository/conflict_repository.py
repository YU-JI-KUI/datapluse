"""Conflict repository — t_conflict"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import Conflict, DataItem

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _conflict_to_dict(c: Conflict, data_content: str | None = None) -> dict[str, Any]:
    return {
        "id": c.id,
        "data_id": c.data_id,
        "data_content": data_content,   # 关联的文本内容，由调用方传入
        "conflict_type": c.conflict_type,
        "detail": c.detail,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "created_by": c.created_by,
    }


class ConflictRepository:
    """Repository for Conflict entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        data_id: int,
        conflict_type: str,
        detail: dict[str, Any],
        created_by: str = "",
    ) -> dict[str, Any]:
        """创建冲突记录（若同类型 open 记录已存在则先关闭）"""
        existing = (
            self.session.query(Conflict)
            .filter(
                Conflict.data_id == data_id,
                Conflict.conflict_type == conflict_type,
                Conflict.status == "open",
            )
            .all()
        )
        for row in existing:
            row.status = "resolved"

        ts = _now()
        c = Conflict(
            data_id=data_id,
            conflict_type=conflict_type,
            detail=detail,
            status="open",
            created_at=ts,
            created_by=created_by,
        )
        self.session.add(c)
        self.session.flush()
        return _conflict_to_dict(c)

    def clear_conflicts(self, data_id: int) -> None:
        """清除某数据的所有 open 冲突（冲突检测重跑时调用）"""
        self.session.query(Conflict).filter(
            Conflict.data_id == data_id, Conflict.status == "open"
        ).delete(synchronize_session=False)

    def get_open_conflicts(self, data_id: int) -> list[dict[str, Any]]:
        rows = (
            self.session.query(Conflict)
            .filter(Conflict.data_id == data_id, Conflict.status == "open")
            .all()
        )
        return [_conflict_to_dict(r) for r in rows]

    def list_by_data(self, data_id: int) -> list[dict[str, Any]]:
        rows = (
            self.session.query(Conflict)
            .filter(Conflict.data_id == data_id)
            .order_by(Conflict.created_at.desc())
            .all()
        )
        return [_conflict_to_dict(r) for r in rows]

    def list_by_dataset(self, dataset_id: int, status: str | None = None) -> list[dict[str, Any]]:
        """通过 t_data_item JOIN 查询某 dataset 下的所有冲突，附带文本内容"""
        q = (
            self.session.query(Conflict, DataItem.content)
            .join(DataItem, DataItem.id == Conflict.data_id)
            .filter(DataItem.dataset_id == dataset_id)
        )
        if status:
            q = q.filter(Conflict.status == status)
        rows = q.order_by(Conflict.created_at.desc()).all()
        return [_conflict_to_dict(conflict, data_content=content) for conflict, content in rows]

    def get_by_id(self, conflict_id: int) -> dict[str, Any] | None:
        row = self.session.get(Conflict, conflict_id)
        if row is None:
            return None
        item = self.session.get(DataItem, row.data_id)
        return _conflict_to_dict(row, data_content=item.content if item else None)

    def resolve(self, conflict_id: int) -> bool:
        row = self.session.get(Conflict, conflict_id)
        if row is None:
            return False
        row.status = "resolved"
        return True

    def has_open_conflict(self, data_id: int) -> bool:
        return (
            self.session.query(Conflict)
            .filter(Conflict.data_id == data_id, Conflict.status == "open")
            .first()
        ) is not None
