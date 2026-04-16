"""User service - business logic for user management."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from datapulse.repository.user_repository import UserRepository


class UserService:
    """Service for user operations."""

    def __init__(self, session: Session) -> None:
        self.repo = UserRepository(session)

    def list_users(self) -> dict[str, Any]:
        """List all users. Returns paginated dict: {"list": [...], "total": N}."""
        return self.repo.list_users()

    def get(self, user_id: int) -> dict[str, Any] | None:
        """Get a user by ID."""
        return self.repo.get(user_id)

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        """Get a user by username."""
        return self.repo.get_by_username(username)

    def create(
        self, username: str, password: str, email: str = "", role_names: list[str] | None = None
    ) -> dict[str, Any]:
        """Create a new user."""
        return self.repo.create(username, password, email, role_names)

    def update(self, user_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a user."""
        return self.repo.update(user_id, data)

    def update_last_login(self, username: str) -> None:
        """Update last login timestamp."""
        self.repo.update_last_login(username)

    def delete(self, user_id: int) -> bool:
        """Delete a user."""
        return self.repo.delete(user_id)

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Verify password against hash."""
        return self.repo.verify_password(plain, hashed)

    def list_roles(self) -> list[dict[str, Any]]:
        """List all roles."""
        return self.repo.list_roles()
