"""Data item repository - CRUD operations on data_items table."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from datapulse.model.entities import DataItem

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _item_to_dict(item: DataItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "dataset_id": item.dataset_id,
        "text": item.text,
        "status": item.status,
        "label": item.label,
        "model_pred": item.model_pred,
        "model_score": item.model_score,
        "annotator": item.annotator,
        "annotated_at": item.annotated_at,
        "conflict_flag": item.conflict_flag or False,
        "conflict_type": item.conflict_type,
        "conflict_detail": item.conflict_detail,
        "source_file": item.source_file,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


class DataRepository:
    """Repository for DataItem entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, dataset_id: int, text: str, source_file: str = "") -> dict[str, Any]:
        ts = _now()
        item = DataItem(
            dataset_id=dataset_id,
            text=text,
            status="raw",
            source_file=source_file,
            created_at=ts,
            updated_at=ts,
        )
        self.session.add(item)
        self.session.flush()
        return _item_to_dict(item)

    def get(self, item_id: int) -> dict[str, Any] | None:
        item = self.session.get(DataItem, item_id)
        return _item_to_dict(item) if item else None

    def update(self, item: dict[str, Any]) -> dict[str, Any]:
        item["updated_at"] = _now()
        row = self.session.get(DataItem, item["id"])
        if row is None:
            row = DataItem(**{k: item.get(k) for k in DataItem.__table__.columns.keys()})
            self.session.add(row)
        else:
            for k, v in item.items():
                if hasattr(row, k):
                    setattr(row, k, v)
        return item

    def delete(self, item_id: int) -> bool:
        row = self.session.get(DataItem, item_id)
        if row is None:
            return False
        self.session.delete(row)
        return True

    def list_all(
        self, dataset_id: int, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        q = self.session.query(DataItem).filter(DataItem.dataset_id == dataset_id)
        if status:
            q = q.filter(DataItem.status == status)
        total = q.count()
        rows = q.order_by(DataItem.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_item_to_dict(r) for r in rows],
        }

    def list_by_status(self, dataset_id: int, status: str) -> list[dict[str, Any]]:
        rows = self.session.query(DataItem).filter(DataItem.dataset_id == dataset_id, DataItem.status == status).all()
        return [_item_to_dict(r) for r in rows]

    def stats(self, dataset_id: int) -> dict[str, int]:
        _statuses = ["raw", "processed", "pre_annotated", "labeling", "labeled", "checked"]
        rows = (
            self.session.query(DataItem.status, func.count(DataItem.id))
            .filter(DataItem.dataset_id == dataset_id)
            .group_by(DataItem.status)
            .all()
        )
        result: dict[str, int] = {st: 0 for st in _statuses}
        result["total"] = 0
        for st, cnt in rows:
            if st in result:
                result[st] = cnt
            result["total"] += cnt
        return result
