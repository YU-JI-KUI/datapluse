"""Dataset repository - CRUD operations on datasets table."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import Dataset, SystemConfig
from datapulse.repository.base import DEFAULT_DATASET_CONFIG

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _dataset_to_dict(d: Dataset) -> dict[str, Any]:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "is_active": d.is_active,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


class DatasetRepository:
    """Repository for Dataset entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_datasets(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        q = self.session.query(Dataset)
        if not include_inactive:
            q = q.filter(Dataset.is_active == True)
        rows = q.order_by(Dataset.id).all()
        return [_dataset_to_dict(r) for r in rows]

    def get(self, dataset_id: int) -> dict[str, Any] | None:
        row = self.session.get(Dataset, dataset_id)
        return _dataset_to_dict(row) if row else None

    def create(self, name: str, description: str = "") -> dict[str, Any]:
        ts = _now()
        row = Dataset(
            name=name,
            description=description,
            is_active=True,
            created_at=ts,
            updated_at=ts,
        )
        self.session.add(row)
        self.session.flush()
        self.session.add(
            SystemConfig(
                dataset_id=row.id,
                config_data=DEFAULT_DATASET_CONFIG,
                updated_at=ts,
                updated_by="system",
            )
        )
        return _dataset_to_dict(row)

    def update(self, dataset_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        row = self.session.get(Dataset, dataset_id)
        if row is None:
            return None
        for field in ("name", "description", "is_active"):
            if field in data:
                setattr(row, field, data[field])
        row.updated_at = _now()
        return _dataset_to_dict(row)

    def delete(self, dataset_id: int) -> bool:
        row = self.session.get(Dataset, dataset_id)
        if row is None:
            return False
        self.session.delete(row)
        return True
