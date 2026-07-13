"""Pipeline repository — t_pipeline_status"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import PipelineStatus

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


class PipelineRepository:
    """Repository for PipelineStatus entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_status(self, dataset_id: int) -> dict[str, Any]:
        row = self.session.get(PipelineStatus, dataset_id)
        if row is None:
            return {"status": "idle", "current_step": "", "progress": 0, "detail": {}}
        return {
            "status":       row.status,
            "current_step": row.current_step or "",
            "progress":     row.progress,
            "detail":       row.detail or {},
            "embed_job":    row.embed_job or {},   # 向量化离线任务状态
            "started_at":   row.started_at.isoformat() if row.started_at else None,
            "finished_at":  row.finished_at.isoformat() if row.finished_at else None,
            "error":        row.error,
            "updated_at":   row.updated_at.isoformat() if row.updated_at else None,
        }

    def try_acquire(self, dataset_id: int, step: str, operator: str = "") -> bool:
        """原子抢占主流程运行权：仅当当前状态不是 running 时置为 running。

        用 SELECT ... FOR UPDATE 行锁替代"先查后写"（check-then-act），
        并发触发时只有一个请求能抢到，其余返回 False。
        行不存在时新建；并发首建撞主键由调用方（DBManager）捕获 IntegrityError 处理。
        """
        row = (
            self.session.query(PipelineStatus)
            .filter(PipelineStatus.dataset_id == dataset_id)
            .with_for_update()
            .one_or_none()
        )
        if row is None:
            row = PipelineStatus(dataset_id=dataset_id)
            self.session.add(row)
        elif row.status == "running":
            return False
        row.status       = "running"
        row.current_step = step
        row.progress     = 0
        row.detail       = {}
        row.started_at   = _now()
        row.finished_at  = None
        row.error        = None
        row.updated_at   = _now()
        row.updated_by   = operator
        return True

    def try_acquire_embed(self, dataset_id: int, operator: str = "") -> bool:
        """原子抢占 embed job 运行权（embed_job 字段与主流程状态互不干扰）。"""
        row = (
            self.session.query(PipelineStatus)
            .filter(PipelineStatus.dataset_id == dataset_id)
            .with_for_update()
            .one_or_none()
        )
        if row is None:
            row = PipelineStatus(dataset_id=dataset_id)
            row.updated_at = _now()
            row.updated_by = operator
            self.session.add(row)
        elif (row.embed_job or {}).get("status") == "running":
            return False
        row.embed_job = {
            "status":     "running",
            "progress":   0,
            "detail":     {},
            "updated_at": str(_now()),
            "updated_by": operator,
        }
        return True

    def set_status(self, dataset_id: int, data: dict[str, Any]) -> None:
        row = self.session.get(PipelineStatus, dataset_id)
        if row is None:
            row = PipelineStatus(dataset_id=dataset_id)
            self.session.add(row)
        row.status       = data.get("status", "idle")
        row.current_step = data.get("current_step", "")
        row.progress     = data.get("progress", 0)
        row.detail       = data.get("detail")
        # embed_job 仅在显式传入时才覆盖，防止主流程进度更新时清除向量化状态
        if "embed_job" in data:
            row.embed_job = data["embed_job"] or None
        # started_at / finished_at 仅在显式传入时才覆盖，防止进度更新时将其清空
        if "started_at" in data and data["started_at"] is not None:
            row.started_at = data["started_at"]
        if "finished_at" in data:
            row.finished_at = data["finished_at"]
        row.error        = data.get("error")
        row.updated_at   = data.get("updated_at") or _now()
        row.updated_by   = data.get("updated_by", "")
