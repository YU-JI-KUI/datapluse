"""
数据集管理 API
- 列表/创建/更新/删除 dataset
- 用户-数据集分配（admin only）
- 普通用户只能看到分配给自己的数据集
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user, require_admin
from datapulse.repository.base import get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
AdminUser = Annotated[UserInfo, Depends(require_admin)]


class DatasetCreate(BaseModel):
    name: str
    description: str | None = ""


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class AssignUsersBody(BaseModel):
    usernames: list[str]


@router.get("")
async def list_datasets(user: CurrentUser):
    """获取当前用户可见的数据集（admin 可见全部，普通用户只见已分配的）"""
    db = get_db()
    datasets = db.list_datasets_for_user(user.username, user.roles)
    return {"success": True, "data": datasets}


@router.get("/all")
async def list_all_datasets(user: AdminUser):
    """管理员获取全部数据集（含 inactive）"""
    db = get_db()
    return {"success": True, "data": db.list_datasets(include_inactive=True)}


@router.post("")
async def create_dataset(body: DatasetCreate, user: AdminUser):
    """创建数据集（同时初始化默认配置）"""
    db = get_db()
    ds = db.create_dataset(name=body.name, description=body.description or "", created_by=user.username)
    return {"success": True, "data": ds}


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: int, user: CurrentUser):
    db = get_db()
    ds = db.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    return {"success": True, "data": ds}


@router.put("/{dataset_id}")
async def update_dataset(dataset_id: int, body: DatasetUpdate, user: AdminUser):
    db = get_db()
    patch: dict = {}
    if body.name is not None:
        patch["name"] = body.name
    if body.description is not None:
        patch["description"] = body.description
    if body.is_active is not None:
        patch["status"] = "active" if body.is_active else "inactive"
    updated = db.update_dataset(dataset_id, patch, updated_by=user.username)
    if not updated:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    return {"success": True, "data": updated}


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: int, user: AdminUser, background_tasks: BackgroundTasks):
    """删除数据集（异步级联删除所有关联数据，包括 DataItem/Annotation/Config 等）"""
    db = get_db()
    # 先确认数据集存在
    ds = db.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    # 立即返回成功，后台异步执行级联删除
    background_tasks.add_task(db.delete_dataset_cascade, dataset_id)
    return {"success": True, "message": f"数据集 {dataset_id} 删除已提交，正在后台清理关联数据"}


@router.get("/{dataset_id}/users")
async def get_dataset_users(dataset_id: int, user: AdminUser):
    """获取数据集已分配的用户列表"""
    db = get_db()
    ds = db.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    usernames = db.get_assigned_users(dataset_id)
    return {"success": True, "data": usernames}


@router.put("/{dataset_id}/users")
async def assign_dataset_users(dataset_id: int, body: AssignUsersBody, user: AdminUser):
    """覆盖式分配用户给数据集"""
    db = get_db()
    ds = db.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    db.assign_users(dataset_id, body.usernames, by=user.username)
    return {"success": True, "message": "分配成功", "data": body.usernames}
