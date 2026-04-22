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

    def batch_resolve(self, conflict_ids: list[int]) -> list[int]:
        """批量关闭冲突（设为 resolved），返回实际更新的 conflict_id 列表。
        调用方负责写 annotation_result + update_stage + 评论。"""
        rows = (
            self.session.query(Conflict)
            .filter(Conflict.id.in_(conflict_ids), Conflict.status == "open")
            .all()
        )
        for row in rows:
            row.status = "resolved"
        return [r.id for r in rows]

    def batch_load_open_conflicts(self, conflict_ids: list[int]) -> dict[int, int]:
        """返回 {conflict_id: data_id}，仅包含 status='open' 的记录（1 次查询）。"""
        if not conflict_ids:
            return {}
        rows = (
            self.session.query(Conflict.id, Conflict.data_id)
            .filter(Conflict.id.in_(conflict_ids), Conflict.status == "open")
            .all()
        )
        return {r.id: r.data_id for r in rows}

    def batch_clear(self, data_ids: list[int]) -> int:
        """批量删除一批 data_id 的 open 冲突（1 次 DELETE IN），返回删除行数。
        用于冲突检测重跑前的清理，替代逐条 clear_conflicts。
        """
        if not data_ids:
            return 0
        return (
            self.session.query(Conflict)
            .filter(Conflict.data_id.in_(data_ids), Conflict.status == "open")
            .delete(synchronize_session=False)
        )

    def batch_create(self, records: list[dict]) -> None:
        """批量插入冲突记录（1 次 INSERT），调用方须先执行 batch_clear。"""
        if not records:
            return
        ts = _now()
        self.session.bulk_insert_mappings(Conflict, [
            {
                "data_id":       r["data_id"],
                "conflict_type": r["conflict_type"],
                "detail":        r["detail"],
                "status":        "open",
                "created_at":    ts,
                "created_by":    r.get("created_by", ""),
            }
            for r in records
        ])

    def batch_revoke(self, conflict_ids: list[int]) -> list[int]:
        """批量撤销自检冲突（设为 revoked），返回对应的 data_id 列表。
        调用方负责将 data item 恢复到 checked stage。"""
        rows = (
            self.session.query(Conflict)
            .filter(Conflict.id.in_(conflict_ids), Conflict.status == "open")
            .all()
        )
        data_ids = []
        for row in rows:
            row.status = "revoked"
            data_ids.append(row.data_id)
        return data_ids

    def list_by_dataset_paged(
        self,
        dataset_id: int,
        status: str | None = None,
        conflict_type: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页查询某 dataset 下的冲突，返回 (records, total)。"""
        q = (
            self.session.query(Conflict, DataItem.content)
            .join(DataItem, DataItem.id == Conflict.data_id)
            .filter(DataItem.dataset_id == dataset_id)
        )
        if status:
            q = q.filter(Conflict.status == status)
        if conflict_type:
            q = q.filter(Conflict.conflict_type == conflict_type)
        if keyword:
            q = q.filter(DataItem.content.ilike(f"%{keyword}%"))

        total = q.count()
        rows = (
            q.order_by(Conflict.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        records = [_conflict_to_dict(c, data_content=content) for c, content in rows]
        return records, total
