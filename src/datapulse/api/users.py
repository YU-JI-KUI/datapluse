"""
用户管理 API（需要管理员权限）
- 用户 CRUD
- 角色列表
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user, require_admin
from datapulse.repository.base import get_db

router = APIRouter()
AdminUser = Annotated[UserInfo, Depends(require_admin)]
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class UserCreate(BaseModel):
    username: str
    password: str
    email: str | None = ""
    role_names: list[str] = ["annotator"]


class UserUpdate(BaseModel):
    email: str | None = None
    is_active: bool | None = None
    password: str | None = None  # 空则不修改密码
    role_names: list[str] | None = None


class ResetPasswordBody(BaseModel):
    new_password: str


@router.get("")
async def list_users(
    user:       AdminUser,
    keyword:    str | None = Query(None,  description="用户名关键字"),
    is_active:  bool | None = Query(None, description="账号状态：true=启用，false=禁用"),
    start_date: str | None = Query(None,  description="更新时间起（YYYY-MM-DD）"),
    end_date:   str | None = Query(None,  description="更新时间止（YYYY-MM-DD）"),
    page:       int = Query(1,  ge=1),
    page_size:  int = Query(20, ge=1, le=200),
):
    """获取用户列表（管理员，支持分页和过滤）"""
    from datapulse.core.response import page_data
    result = get_db().list_users(
        keyword=keyword, is_active=is_active,
        start_date=start_date, end_date=end_date,
        page=page, page_size=page_size,
    )
    return {"success": True, "data": page_data(result["list"], page, page_size, result["total"])}


@router.get("/roles")
async def list_roles(user: CurrentUser):
    """获取所有可用角色（供创建/编辑用户时选择）"""
    return {"success": True, "data": get_db().list_roles()}


@router.post("")
async def create_user(body: UserCreate, user: AdminUser):
    """创建新用户（管理员）"""
    db = get_db()
    username = body.username.strip().upper()   # 用户名统一大写
    if not username:
        raise HTTPException(400, "用户名不能为空")
    if db.get_user_by_username(username):
        raise HTTPException(400, f"用户名已存在: {username}")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    new_user = db.create_user(
        username=username,
        password=body.password,
        email=body.email or "",
        role_names=body.role_names,
        created_by=user.username,
    )
    return {"success": True, "data": new_user}


@router.get("/{user_id}")
async def get_user(user_id: int, user: AdminUser):
    """获取单个用户详情（管理员）"""
    target = get_db().get_user(user_id)
    if not target:
        raise HTTPException(404, f"用户不存在: {user_id}")
    return {"success": True, "data": target}


@router.put("/{user_id}")
async def update_user(user_id: int, body: UserUpdate, user: AdminUser):
    """更新用户信息/角色/状态（管理员）"""
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
    updated = get_db().update_user(user_id, patch, updated_by=user.username)
    if not updated:
        raise HTTPException(404, f"用户不存在: {user_id}")
    return {"success": True, "data": updated}


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: int, body: ResetPasswordBody, user: AdminUser):
    """重置用户密码（管理员专用，不需要知道旧密码）"""
    if len(body.new_password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    updated = get_db().update_user(user_id, {"password": body.new_password}, updated_by=user.username)
    if not updated:
        raise HTTPException(404, f"用户不存在: {user_id}")
    return {"success": True, "message": "密码已重置"}


@router.delete("/{user_id}")
async def delete_user(user_id: int, user: AdminUser):
    """删除用户（管理员，不可删除自己）"""
    if user_id == user.user_id:
        raise HTTPException(400, "不能删除自己的账号")
    if not get_db().delete_user(user_id):
        raise HTTPException(404, f"用户不存在: {user_id}")
    return {"success": True, "message": f"已删除用户 {user_id}"}
