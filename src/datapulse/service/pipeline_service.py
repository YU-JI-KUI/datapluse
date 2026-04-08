"""Pipeline service - business logic for pipeline operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from datapulse.repository.pipeline_repository import PipelineRepository


class PipelineService:
    """Service for pipeline operations."""

    def __init__(self, session: Session) -> None:
        self.repo = PipelineRepository(session)

    def get_status(self, dataset_id: int) -> dict[str, Any]:
        """Get pipeline status for a dataset."""
        return self.repo.get_status(dataset_id)

    def set_status(self, dataset_id: int, data: dict[str, Any]) -> None:
        """Set pipeline status for a dataset."""
        self.repo.set_status(dataset_id, data)
