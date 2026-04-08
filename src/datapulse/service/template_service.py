"""Template service - business logic for export templates."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from datapulse.repository.template_repository import TemplateRepository


class TemplateService:
    """Service for export template operations."""

    def __init__(self, session: Session) -> None:
        self.repo = TemplateRepository(session)

    def list_templates(self, dataset_id: int) -> list[dict[str, Any]]:
        """List templates for a dataset."""
        return self.repo.list_templates(dataset_id)

    def get(self, template_id: int) -> dict[str, Any] | None:
        """Get a template by ID."""
        return self.repo.get(template_id)

    def create(self, dataset_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new template."""
        return self.repo.create(dataset_id, data)

    def update(self, template_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a template."""
        return self.repo.update(template_id, data)

    def delete(self, template_id: int) -> bool:
        """Delete a template."""
        return self.repo.delete(template_id)
