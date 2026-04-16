"""User repository — t_user + t_role + t_user_role（username 逻辑外键）"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import Role, User, UserRole
from datapulse.repository.base import _hash_password, _verify_password

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _user_to_dict(u: User, roles: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email or "",
        "is_active": u.is_active,
        "roles": roles or [],
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "updated_at": u.updated_at.isoformat() if u.updated_at else None,
    }


def _role_to_dict(r: Role) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "permissions": r.permissions or [],
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


class UserRepository:
    """Repository for User entity（角色关联通过 username 逻辑外键）"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _get_user_roles(self, username: str) -> list[str]:
        """通过 username 获取角色名列表（直接查 t_user_role，无需 JOIN role 表）"""
        rows = (
            self.session.query(UserRole.role_name)
            .filter(UserRole.username == username)
            .all()
        )
        return [r[0] for r in rows]

    def list_users(
        self,
        keyword: str | None = None,
        is_active: bool | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        q = self.session.query(User)
        if keyword:
            q = q.filter(User.username.ilike(f"%{keyword}%"))
        if is_active is not None:
            q = q.filter(User.is_active == is_active)
        if start_date:
            q = q.filter(User.updated_at >= start_date)
        if end_date:
            q = q.filter(User.updated_at <= end_date + " 23:59:59")
        total = q.count()
        users = q.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "list": [_user_to_dict(u, self._get_user_roles(u.username)) for u in users],
            "total": total,
        }

    def get(self, user_id: int) -> dict[str, Any] | None:
        u = self.session.get(User, user_id)
        if u is None:
            return None
        return _user_to_dict(u, self._get_user_roles(u.username))

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        u = self.session.query(User).filter(User.username == username).first()
        if u is None:
            return None
        d = _user_to_dict(u, self._get_user_roles(username))
        d["password_hash"] = u.password_hash  # 仅供认证使用
        return d

    def create(
        self,
        username: str,
        password: str,
        email: str = "",
        role_names: list[str] | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        ts = _now()
        user = User(
            username=username,
            email=email,
            password_hash=_hash_password(password),
            is_active=True,
            created_at=ts,
            created_by=created_by,
            updated_at=ts,
            updated_by=created_by,
        )
        self.session.add(user)
        self.session.flush()

        roles: list[str] = []
        for rname in role_names or ["annotator"]:
            # 校验角色是否存在
            exists = self.session.query(Role).filter(Role.name == rname).first()
            if exists:
                self.session.add(
                    UserRole(username=username, role_name=rname, created_at=ts, created_by=created_by)
                )
                roles.append(rname)
        return _user_to_dict(user, roles)

    def update(self, user_id: int, data: dict[str, Any], updated_by: str = "system") -> dict[str, Any] | None:
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
            # 删除旧绑定，重新写入
            self.session.query(UserRole).filter(UserRole.username == u.username).delete()
            ts = _now()
            for rname in data["role_names"]:
                exists = self.session.query(Role).filter(Role.name == rname).first()
                if exists:
                    self.session.add(
                        UserRole(username=u.username, role_name=rname, created_at=ts, created_by=updated_by)
                    )
        u.updated_at = _now()
        u.updated_by = updated_by
        return _user_to_dict(u, self._get_user_roles(u.username))

    def update_last_login(self, username: str) -> None:
        u = self.session.query(User).filter(User.username == username).first()
        if u:
            u.last_login_at = _now()

    def delete(self, user_id: int) -> bool:
        u = self.session.get(User, user_id)
        if u is None:
            return False
        self.session.query(UserRole).filter(UserRole.username == u.username).delete()
        self.session.delete(u)
        return True

    def verify_password(self, plain: str, hashed: str) -> bool:
        return _verify_password(plain, hashed)

    def list_roles(self) -> list[dict[str, Any]]:
        rows = self.session.query(Role).order_by(Role.id).all()
        return [_role_to_dict(r) for r in rows]
