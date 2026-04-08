"""
数据集管理 API
- 列表/创建/更新/删除 dataset
- dataset 是数据、配置、模板的隔离单元
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user, require_admin
from storage.db import get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
AdminUser   = Annotated[UserInfo, Depends(require_admin)]


class DatasetCreate(BaseModel):
    name: str
    description: Optional[str] = ""


class DatasetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_datasets(user: CurrentUser):
    """获取所有启用的数据集"""
    db = get_db()
    return {"success": True, "data": db.list_datasets(include_inactive=False)}


@router.post("")
async def create_dataset(body: DatasetCreate, user: AdminUser):
    """创建数据集（同时初始化默认配置）"""
    db = get_db()
    ds = db.create_dataset(name=body.name, description=body.description or "")
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
        patch["is_active"] = body.is_active
    updated = db.update_dataset(dataset_id, patch)
    if not updated:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    return {"success": True, "data": updated}


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: int, user: AdminUser):
    """删除数据集（级联删除所有关联数据，谨慎操作）"""
    db = get_db()
    ok = db.delete_dataset(dataset_id)
    if not ok:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    return {"success": True, "message": f"已删除数据集 {dataset_id}"}
