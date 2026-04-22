"""Comment repository — t_data_comment"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import DataComment

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _comment_to_dict(c: DataComment) -> dict[str, Any]:
    return {
        "id": c.id,
        "data_id": c.data_id,
        "username": c.username,
        "comment": c.comment,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "created_by": c.created_by,
    }


class CommentRepository:
    """Repository for DataComment entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, data_id: int, username: str, comment: str) -> dict[str, Any]:
        ts = _now()
        row = DataComment(
            data_id=data_id,
            username=username,
            comment=comment,
            created_at=ts,
            created_by=username,
        )
        self.session.add(row)
        self.session.flush()
        return _comment_to_dict(row)

    def bulk_create(self, records: list[dict[str, Any]]) -> None:
        """批量插入评论（1 次 INSERT）。
        records 每项须含 data_id, username, comment；可选 created_by。
        """
        if not records:
            return
        ts = _now()
        self.session.bulk_insert_mappings(DataComment, [
            {
                "data_id":    r["data_id"],
                "username":   r["username"],
                "comment":    r["comment"],
                "created_at": ts,
                "created_by": r.get("created_by", r["username"]),
            }
            for r in records
        ])

    def list_by_data(self, data_id: int) -> list[dict[str, Any]]:
        rows = (
            self.session.query(DataComment)
            .filter(DataComment.data_id == data_id)
            .order_by(DataComment.created_at.asc())
            .all()
        )
        return [_comment_to_dict(r) for r in rows]

    def delete(self, comment_id: int, username: str) -> bool:
        """只允许评论本人删除"""
        row = self.session.get(DataComment, comment_id)
        if row is None or row.username != username:
            return False
        self.session.delete(row)
        return True
