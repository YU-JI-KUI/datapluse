"""
认证模块（RBAC）
- 用户从 PostgreSQL 读取，不依赖 config.yaml
- JWT Token（HS256），payload 含 user_id + roles
- 权限检查：has_permission() / require_admin
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

from datapulse.config.settings import get_settings
from datapulse.repository import get_db

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

ACCESS_TOKEN_EXPIRE_HOURS = 24


# ── Schemas ────────────────────────────────────────────────────────────────


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    roles: list[str]


class UserInfo(BaseModel):
    user_id: int
    username: str
    roles: list[str] = []

    def is_admin(self) -> bool:
        return "admin" in self.roles

    def has_permission(self, perm: str) -> bool:
        """检查是否拥有某权限。admin 角色拥有全部权限。"""
        from sqlalchemy.orm import sessionmaker

        from datapulse.repository.base import _db
        from datapulse.service.user_service import UserService

        if _db is None:
            return False
        session_class = sessionmaker(bind=_db._engine)
        session = session_class()
        try:
            user_service = UserService(session)
            for role in user_service.list_roles():
                if role["name"] in self.roles:
                    perms = role.get("permissions", [])
                    if "*" in perms or perm in perms:
                        return True
            return False
        finally:
            session.close()


# ── Token 工具 ─────────────────────────────────────────────────────────────


def _create_token(user_id: int, username: str, roles: list[str]) -> str:
    settings = get_settings()
    payload = {
        "sub": username,
        "user_id": user_id,
        "roles": roles,
        "exp": datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err


# ── 依赖注入 ───────────────────────────────────────────────────────────────


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> UserInfo:
    payload = _decode_token(token)
    username = payload.get("sub")
    user_id = payload.get("user_id")
    roles = payload.get("roles", [])
    if not username or user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token 格式错误")
    # 检查用户是否仍然有效（防止停用账号继续使用旧 token）
    db = get_db()
    from sqlalchemy.orm import sessionmaker

    from datapulse.service.user_service import UserService

    session_class = sessionmaker(bind=db._engine)
    session = session_class()
    try:
        user_service = UserService(session)
        user = user_service.get(int(user_id))
        if user is None or not user["is_active"]:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号已停用或不存在")
    finally:
        session.close()
    return UserInfo(user_id=int(user_id), username=username, roles=roles)


def require_admin(user: Annotated[UserInfo, Depends(get_current_user)]) -> UserInfo:
    """管理员专属接口的依赖"""
    if not user.is_admin():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


# ── 路由 ───────────────────────────────────────────────────────────────────


@router.post("/login", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    from sqlalchemy.orm import sessionmaker

    from datapulse.service.user_service import UserService

    session_class = sessionmaker(bind=db._engine)
    session = session_class()
    try:
        user_service = UserService(session)
        user = user_service.get_by_username(form.username)
        if user is None or not user.get("is_active"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
        if not user_service.verify_password(form.password, user["password_hash"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")

        user_service.update_last_login(user["username"])
        session.commit()   # ← 必须 commit，否则 last_login_at 不会持久化
        token = _create_token(user["id"], user["username"], user["roles"])
        return Token(
            access_token=token,
            token_type="bearer",
            username=user["username"],
            roles=user["roles"],
        )
    finally:
        session.close()


@router.get("/me")
async def me(user: Annotated[UserInfo, Depends(get_current_user)]):
    return {
        "success": True,
        "data": {
            "user_id": user.user_id,
            "username": user.username,
            "roles": user.roles,
        },
    }


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    body: ChangePasswordBody,
    user: Annotated[UserInfo, Depends(get_current_user)],
):
    """已登录用户修改自己的密码（需验证旧密码）"""
    if len(body.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")

    db = get_db()
    from sqlalchemy.orm import sessionmaker

    from datapulse.service.user_service import UserService

    session_class = sessionmaker(bind=db._engine)
    session = session_class()
    try:
        user_service = UserService(session)
        current = user_service.get_by_username(user.username)
        if current is None:
            raise HTTPException(404, "用户不存在")
        if not user_service.verify_password(body.old_password, current["password_hash"]):
            raise HTTPException(400, "旧密码不正确")
        user_service.update(current["id"], {"password": body.new_password})
        session.commit()
        return {"success": True, "message": "密码已更新"}
    finally:
        session.close()
