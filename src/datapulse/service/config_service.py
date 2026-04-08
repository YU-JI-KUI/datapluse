"""Config service - business logic for system configuration."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from datapulse.repository.config_repository import ConfigRepository


class ConfigService:
    """Service for configuration operations."""

    def __init__(self, session: Session) -> None:
        self.repo = ConfigRepository(session)

    def get_dataset_config(self, dataset_id: int) -> dict[str, Any]:
        """Get dataset configuration."""
        return self.repo.get_dataset_config(dataset_id)

    def set_dataset_config(
        self, dataset_id: int, config_data: dict[str, Any], updated_by: str = "system"
    ) -> dict[str, Any]:
        """Set dataset configuration."""
        return self.repo.set_dataset_config(dataset_id, config_data, updated_by)
