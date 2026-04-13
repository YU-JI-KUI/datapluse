"""Template repository — t_export_template"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import ExportTemplate
from datapulse.repository.base import DEFAULT_COLUMNS

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _template_to_dict(t: ExportTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "dataset_id": t.dataset_id,
        "name": t.name,
        "description": t.description,
        "format": t.format,
        "columns": t.columns or DEFAULT_COLUMNS,
        "filters": t.filters or {"status": "checked", "include_conflicts": False},
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "created_by": t.created_by,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "updated_by": t.updated_by,
    }


class TemplateRepository:
    """Repository for ExportTemplate entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_templates(self, dataset_id: int) -> list[dict[str, Any]]:
        rows = (
            self.session.query(ExportTemplate)
            .filter(ExportTemplate.dataset_id == dataset_id)
            .order_by(ExportTemplate.created_at.desc())
            .all()
        )
        return [_template_to_dict(r) for r in rows]

    def get(self, template_id: int) -> dict[str, Any] | None:
        row = self.session.get(ExportTemplate, template_id)
        return _template_to_dict(row) if row else None

    def create(self, dataset_id: int, data: dict[str, Any], created_by: str = "") -> dict[str, Any]:
        ts = _now()
        row = ExportTemplate(
            dataset_id=dataset_id,
            name=data["name"],
            description=data.get("description", ""),
            format=data.get("format", "json"),
            columns=data.get("columns", DEFAULT_COLUMNS),
            filters=data.get("filters", {"status": "checked", "include_conflicts": False}),
            created_at=ts,
            created_by=created_by,
            updated_at=ts,
            updated_by=created_by,
        )
        self.session.add(row)
        self.session.flush()
        return _template_to_dict(row)

    def update(self, template_id: int, data: dict[str, Any], updated_by: str = "") -> dict[str, Any] | None:
        row = self.session.get(ExportTemplate, template_id)
        if row is None:
            return None
        for field in ("name", "description", "format", "columns", "filters"):
            if field in data:
                setattr(row, field, data[field])
        row.updated_at = _now()
        row.updated_by = updated_by
        return _template_to_dict(row)

    def delete(self, template_id: int) -> bool:
        row = self.session.get(ExportTemplate, template_id)
        if row is None:
            return False
        self.session.delete(row)
        return True
