"""User repository - CRUD operations on users, roles, and user_roles tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import Role, User, UserRole
from datapulse.repository.base import _hash_password, _verify_password

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _user_to_dict(u: User, roles: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email or "",
        "is_active": u.is_active,
        "roles": roles or [],
        "created_at": u.created_at,
        "updated_at": u.updated_at,
        "last_login_at": u.last_login_at,
    }


def _role_to_dict(r: Role) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "permissions": r.permissions or [],
        "created_at": r.created_at,
    }


class UserRepository:
    """Repository for User entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _get_user_roles(self, user_id: int) -> list[str]:
        rows = (
            self.session.query(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .filter(UserRole.user_id == user_id)
            .all()
        )
        return [r[0] for r in rows]

    def list_users(self) -> list[dict[str, Any]]:
        users = self.session.query(User).order_by(User.id).all()
        return [_user_to_dict(u, self._get_user_roles(u.id)) for u in users]

    def get(self, user_id: int) -> dict[str, Any] | None:
        u = self.session.get(User, user_id)
        if u is None:
            return None
        return _user_to_dict(u, self._get_user_roles(user_id))

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        u = self.session.query(User).filter(User.username == username).first()
        if u is None:
            return None
        d = _user_to_dict(u, self._get_user_roles(u.id))
        d["password_hash"] = u.password_hash  # 仅供认证使用
        return d

    def create(
        self, username: str, password: str, email: str = "", role_names: list[str] | None = None
    ) -> dict[str, Any]:
        ts = _now()
        user = User(
            username=username,
            email=email,
            password_hash=_hash_password(password),
            is_active=True,
            created_at=ts,
            updated_at=ts,
        )
        self.session.add(user)
        self.session.flush()
        roles: list[str] = []
        for rname in role_names or ["annotator"]:
            role = self.session.query(Role).filter(Role.name == rname).first()
            if role:
                self.session.add(UserRole(user_id=user.id, role_id=role.id, created_at=ts))
                roles.append(rname)
        return _user_to_dict(user, roles)

    def update(self, user_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        u = self.session.get(User, user_id)
        if u is None:
            return None
        if "email" in data:
            u.email = data["email"]
        if "is_active" in data:
            u.is_active = data["is_active"]
        if "password" in data and data["password"]:
            u.password_hash = _hash_password(data["password"])
        if "role_names" in data:
            self.session.query(UserRole).filter(UserRole.user_id == user_id).delete()
            for rname in data["role_names"]:
                role = self.session.query(Role).filter(Role.name == rname).first()
                if role:
                    self.session.add(UserRole(user_id=user_id, role_id=role.id, created_at=_now()))
        u.updated_at = _now()
        roles = self._get_user_roles(user_id)
        return _user_to_dict(u, roles)

    def update_last_login(self, user_id: int) -> None:
        u = self.session.get(User, user_id)
        if u:
            u.last_login_at = _now()

    def delete(self, user_id: int) -> bool:
        u = self.session.get(User, user_id)
        if u is None:
            return False
        self.session.delete(u)
        return True

    def verify_password(self, plain: str, hashed: str) -> bool:
        return _verify_password(plain, hashed)

    def list_roles(self) -> list[dict[str, Any]]:
        rows = self.session.query(Role).order_by(Role.id).all()
        return [_role_to_dict(r) for r in rows]
