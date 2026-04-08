"""Dataset service - business logic for datasets."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from datapulse.repository.dataset_repository import DatasetRepository


class DatasetService:
    """Service for dataset operations."""

    def __init__(self, session: Session) -> None:
        self.repo = DatasetRepository(session)

    def list_datasets(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        """List all datasets."""
        return self.repo.list_datasets(include_inactive)

    def get(self, dataset_id: int) -> dict[str, Any] | None:
        """Get a dataset by ID."""
        return self.repo.get(dataset_id)

    def create(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a new dataset."""
        return self.repo.create(name, description)

    def update(self, dataset_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a dataset."""
        return self.repo.update(dataset_id, data)

    def delete(self, dataset_id: int) -> bool:
        """Delete a dataset."""
        return self.repo.delete(dataset_id)
