"""
导出模板 CRUD API
模板定义了导出时的字段映射、输出格式和过滤条件
"""
from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user
from storage.db import get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class ColumnDef(BaseModel):
    source: str          # 源字段名，如 "text"
    target: str          # 输出字段名，如 "sentence"
    include: bool = True


class TemplateFilters(BaseModel):
    status: str = "checked"
    include_conflicts: bool = False


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    format: str = "json"             # json | excel | csv
    columns: List[ColumnDef]
    filters: TemplateFilters = TemplateFilters()


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    format: Optional[str] = None
    columns: Optional[List[ColumnDef]] = None
    filters: Optional[TemplateFilters] = None


@router.get("")
async def list_templates(user: CurrentUser):
    """获取所有导出模板"""
    db = get_db()
    return {"success": True, "data": db.list_templates()}


@router.post("")
async def create_template(body: TemplateCreate, user: CurrentUser):
    """创建新模板"""
    db = get_db()
    data = {
        "name": body.name,
        "description": body.description,
        "format": body.format,
        "columns": [c.model_dump() for c in body.columns],
        "filters": body.filters.model_dump(),
    }
    tpl = db.create_template(data)
    return {"success": True, "data": tpl}


@router.get("/{template_id}")
async def get_template(template_id: str, user: CurrentUser):
    """获取单个模板"""
    db = get_db()
    tpl = db.get_template(template_id)
    if not tpl:
        raise HTTPException(404, f"模板不存在: {template_id}")
    return {"success": True, "data": tpl}


@router.put("/{template_id}")
async def update_template(template_id: str, body: TemplateUpdate, user: CurrentUser):
    """更新模板"""
    db = get_db()
    patch = {}
    if body.name is not None:
        patch["name"] = body.name
    if body.description is not None:
        patch["description"] = body.description
    if body.format is not None:
        patch["format"] = body.format
    if body.columns is not None:
        patch["columns"] = [c.model_dump() for c in body.columns]
    if body.filters is not None:
        patch["filters"] = body.filters.model_dump()

    tpl = db.update_template(template_id, patch)
    if not tpl:
        raise HTTPException(404, f"模板不存在: {template_id}")
    return {"success": True, "data": tpl}


@router.delete("/{template_id}")
async def delete_template(template_id: str, user: CurrentUser):
    """删除模板"""
    db = get_db()
    ok = db.delete_template(template_id)
    if not ok:
        raise HTTPException(404, f"模板不存在: {template_id}")
    return {"success": True, "message": f"已删除模板 {template_id}"}
