"""Dataset repository — t_dataset + t_system_config"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import Dataset, SystemConfig
from datapulse.repository.base import DEFAULT_DATASET_CONFIG

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _dataset_to_dict(d: Dataset) -> dict[str, Any]:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "status": d.status,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "created_by": d.created_by,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "updated_by": d.updated_by,
    }


class DatasetRepository:
    """Repository for Dataset entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_datasets(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        q = self.session.query(Dataset)
        if not include_inactive:
            q = q.filter(Dataset.status == "active")
        rows = q.order_by(Dataset.id).all()
        return [_dataset_to_dict(r) for r in rows]

    def get(self, dataset_id: int) -> dict[str, Any] | None:
        row = self.session.get(Dataset, dataset_id)
        return _dataset_to_dict(row) if row else None

    def create(self, name: str, description: str = "", created_by: str = "system") -> dict[str, Any]:
        ts = _now()
        row = Dataset(
            name=name,
            description=description,
            status="active",
            created_at=ts,
            created_by=created_by,
            updated_at=ts,
            updated_by=created_by,
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

    def update(self, dataset_id: int, data: dict[str, Any], updated_by: str = "system") -> dict[str, Any] | None:
        row = self.session.get(Dataset, dataset_id)
        if row is None:
            return None
        for field in ("name", "description", "status"):
            if field in data:
                setattr(row, field, data[field])
        row.updated_at = _now()
        row.updated_by = updated_by
        return _dataset_to_dict(row)

    def delete(self, dataset_id: int) -> bool:
        row = self.session.get(Dataset, dataset_id)
        if row is None:
            return False
        self.session.delete(row)
        return True
