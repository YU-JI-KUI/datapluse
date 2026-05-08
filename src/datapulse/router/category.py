"""
业务分类路由

GET    /api/categories          — 分页查询（by dataset_id）
POST   /api/categories          — 新建分类
PATCH  /api/categories/{id}     — 更新分类
DELETE /api/categories/{id}     — 删除分类
POST   /api/categories/upload   — Excel 批量导入（两列：业务名 / 业务介绍）
"""

from __future__ import annotations

import io
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import NotFoundError, ParamError
from datapulse.core.response import page_data, success
from datapulse.repository.base import get_db

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


# ── schemas ───────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    dataset_id:  int
    name:        str
    description: str = ""


class CategoryUpdate(BaseModel):
    name:        str | None = None
    description: str | None = None


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_categories(
    _user:      CurrentUser,
    dataset_id: int        = Query(...),
    keyword:    str | None = Query(None),
    page:       int        = Query(1,  ge=1),
    page_size:  int        = Query(10, ge=1, le=100),
):
    db     = get_db()
    result = db.list_categories(dataset_id, keyword=keyword, page=page, page_size=page_size)
    return success(page_data(result["list"], page, page_size, result["total"]))


@router.post("")
async def create_category(body: CategoryCreate, user: CurrentUser):
    if not body.name.strip():
        raise ParamError("分类名称不能为空")
    db  = get_db()
    row = db.create_category(
        dataset_id  = body.dataset_id,
        name        = body.name,
        description = body.description,
        created_by  = user.username,
    )
    return success(row)


@router.patch("/{category_id}")
async def update_category(category_id: int, body: CategoryUpdate, user: CurrentUser):
    db  = get_db()
    row = db.update_category(
        category_id = category_id,
        name        = body.name,
        description = body.description,
        updated_by  = user.username,
    )
    if not row:
        raise NotFoundError(f"分类不存在: id={category_id}")
    return success(row)


@router.delete("/{category_id}")
async def delete_category(category_id: int, user: CurrentUser):
    db  = get_db()
    ok  = db.delete_category(category_id)
    if not ok:
        raise NotFoundError(f"分类不存在: id={category_id}")
    return success({"deleted_id": category_id})


class BulkDeleteBody(BaseModel):
    ids: list[int]


@router.post("/bulk-delete")
async def bulk_delete_categories(body: BulkDeleteBody, user: CurrentUser):
    if not body.ids:
        raise ParamError("ids 不能为空")
    deleted = get_db().bulk_delete_categories(body.ids)
    return success({"deleted": deleted})


@router.post("/upload")
async def upload_categories(
    user:       CurrentUser,
    dataset_id: int        = Form(...),
    file:       UploadFile = File(...),
):
    """Excel 批量导入业务分类。

    Excel 格式（第一行为表头，列顺序不限，按列名匹配）：
      - 业务名   / name        — 分类名称（必填）
      - 业务介绍 / description — 分类介绍（可选）
    """
    filename = file.filename or ""
    if not filename.endswith((".xlsx", ".xls")):
        raise ParamError("仅支持 Excel 文件（.xlsx / .xls）")

    content = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    except Exception as e:
        raise ParamError(f"Excel 解析失败：{e}") from e

    # 列名归一化：支持中文别名
    col_map = {}
    for col in df.columns:
        low = str(col).strip().lower()
        if low in ("业务名", "name", "分类名", "分类名称"):
            col_map["name"] = col
        elif low in ("业务介绍", "description", "介绍", "描述", "说明"):
            col_map["description"] = col

    if "name" not in col_map:
        raise ParamError("Excel 必须包含「业务名」或「name」列")

    records = []
    for _, row in df.iterrows():
        name = str(row[col_map["name"]]).strip() if col_map.get("name") else ""
        desc = ""
        if "description" in col_map:
            raw = row[col_map["description"]]
            desc = "" if (pd.isna(raw) if hasattr(pd, "isna") else raw != raw) else str(raw).strip()
        if name and name.lower() != "nan":
            records.append({"name": name, "description": desc})

    if not records:
        raise ParamError("Excel 中没有有效数据行")

    result = get_db().bulk_create_categories(dataset_id, records, created_by=user.username)
    return success({**result, "total_rows": len(records)})
