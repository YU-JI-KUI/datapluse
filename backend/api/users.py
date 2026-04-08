"""
用户管理 API（需要管理员权限）
- 用户 CRUD
- 角色列表
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user, require_admin
from storage.db import get_db

router = APIRouter()
AdminUser = Annotated[UserInfo, Depends(require_admin)]
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = ""
    role_names: list[str] = ["annotator"]


class UserUpdate(BaseModel):
    email: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None        # 为空则不修改密码
    role_names: Optional[list[str]] = None


@router.get("")
async def list_users(user: AdminUser):
    """获取所有用户列表（管理员）"""
    db = get_db()
    return {"success": True, "data": db.list_users()}


@router.post("")
async def create_user(body: UserCreate, user: AdminUser):
    """创建新用户（管理员）"""
    db = get_db()
    # 检查用户名是否重复
    if db.get_user_by_username(body.username):
        raise HTTPException(400, f"用户名已存在: {body.username}")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    new_user = db.create_user(
        username=body.username,
        password=body.password,
        email=body.email or "",
        role_names=body.role_names,
    )
    return {"success": True, "data": new_user}


@router.get("/roles")
async def list_roles(user: CurrentUser):
    """获取所有可用角色（供创建/编辑用户时选择）"""
    db = get_db()
    return {"success": True, "data": db.list_roles()}


@router.get("/{user_id}")
async def get_user(user_id: str, user: AdminUser):
    """获取单个用户详情（管理员）"""
    db = get_db()
    target = db.get_user(user_id)
    if not target:
        raise HTTPException(404, f"用户不存在: {user_id}")
    return {"success": True, "data": target}


@router.put("/{user_id}")
async def update_user(user_id: str, body: UserUpdate, user: AdminUser):
    """更新用户信息/角色/状态（管理员）"""
    db = get_db()
    # 防止管理员停用自己
    if user_id == user.user_id and body.is_active is False:
        raise HTTPException(400, "不能停用自己的账号")
    patch: dict = {}
    if body.email is not None:
        patch["email"] = body.email
    if body.is_active is not None:
        patch["is_active"] = body.is_active
    if body.password:
        if len(body.password) < 6:
            raise HTTPException(400, "密码至少 6 位")
        patch["password"] = body.password
    if body.role_names is not None:
        patch["role_names"] = body.role_names
    updated = db.update_user(user_id, patch)
    if not updated:
        raise HTTPException(404, f"用户不存在: {user_id}")
    return {"success": True, "data": updated}


@router.delete("/{user_id}")
async def delete_user(user_id: str, user: AdminUser):
    """删除用户（管理员，不可删除自己）"""
    if user_id == user.user_id:
        raise HTTPException(400, "不能删除自己的账号")
    db = get_db()
    ok = db.delete_user(user_id)
    if not ok:
        raise HTTPException(404, f"用户不存在: {user_id}")
    return {"success": True, "message": f"已删除用户 {user_id}"}
