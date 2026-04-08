"""Data service - business logic for data items."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from datapulse.repository.data_repository import DataRepository


class DataService:
    """Service for data item operations."""

    def __init__(self, session: Session) -> None:
        self.repo = DataRepository(session)

    def create(self, dataset_id: int, text: str, source_file: str = "") -> dict[str, Any]:
        """Create a new data item."""
        return self.repo.create(dataset_id, text, source_file)

    def get(self, item_id: int) -> dict[str, Any] | None:
        """Get a data item by ID."""
        return self.repo.get(item_id)

    def update(self, item: dict[str, Any]) -> dict[str, Any]:
        """Update a data item."""
        return self.repo.update(item)

    def delete(self, item_id: int) -> bool:
        """Delete a data item."""
        return self.repo.delete(item_id)

    def list_all(
        self, dataset_id: int, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        """List data items with pagination."""
        return self.repo.list_all(dataset_id, status, page, page_size)

    def list_by_status(self, dataset_id: int, status: str) -> list[dict[str, Any]]:
        """List data items by status."""
        return self.repo.list_by_status(dataset_id, status)

    def stats(self, dataset_id: int) -> dict[str, int]:
        """Get statistics for data items."""
        return self.repo.stats(dataset_id)
