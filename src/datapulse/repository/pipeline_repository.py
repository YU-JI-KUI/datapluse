"""Pipeline repository - CRUD operations on pipeline_status table."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import PipelineStatus

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


class PipelineRepository:
    """Repository for PipelineStatus entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_status(self, dataset_id: int) -> dict[str, Any]:
        row = self.session.get(PipelineStatus, dataset_id)
        if row is None:
            return {"status": "idle", "current_step": None, "progress": 0, "detail": {}}
        return {
            "status": row.status,
            "current_step": row.current_step,
            "progress": row.progress,
            "detail": row.detail or {},
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "error": row.error,
            "updated_at": row.updated_at,
        }

    def set_status(self, dataset_id: int, data: dict[str, Any]) -> None:
        row = self.session.get(PipelineStatus, dataset_id)
        if row is None:
            row = PipelineStatus(dataset_id=dataset_id)
            self.session.add(row)
        row.status = data.get("status", "idle")
        row.current_step = data.get("current_step")
        row.progress = data.get("progress", 0)
        row.detail = data.get("detail")
        row.started_at = data.get("started_at")
        row.finished_at = data.get("finished_at")
        row.error = data.get("error")
        row.updated_at = data.get("updated_at", _now())
