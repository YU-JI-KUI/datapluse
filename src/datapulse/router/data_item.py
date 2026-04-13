"""
数据管理路由
GET  /api/data-items          — 分页列表（支持 keyword / status 过滤）
GET  /api/data-items/{id}     — 详情（含标注、评论、冲突）
POST /api/data-items/upload   — 文件上传
DELETE /api/data-items/{id}   — 删除
GET  /api/data-items/stats    — 各阶段统计
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import NotFoundError, ParamError
from datapulse.core.response import page_data, success
from datapulse.modules.processing import is_valid, parse_file
from datapulse.repository.base import get_db

router     = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class CreateDataItemBody(BaseModel):
    dataset_id: int
    content:    str
    source_ref: str = ""


@router.post("")
async def create_data_item(body: CreateDataItemBody, user: CurrentUser):
    """手动录入单条数据"""
    if not body.content or not body.content.strip():
        raise ParamError("内容不能为空")
    db = get_db()
    if not db.get_dataset(body.dataset_id):
        raise NotFoundError(f"数据集不存在: {body.dataset_id}")
    result = db.create_data(
        body.dataset_id,
        content=body.content.strip(),
        source="manual",
        source_ref=body.source_ref or "手动录入",
        created_by=user.username,
    )
    if result is None:
        raise ParamError("数据已存在（重复内容）")
    return success(result)


@router.get("")
async def list_data_items(
    user:       CurrentUser,
    dataset_id: int           = Query(..., description="数据集 ID"),
    status:     str | None    = Query(None, description="按阶段过滤"),
    keyword:    str | None    = Query(None, description="文本关键词搜索"),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(20, ge=1, le=200),
):
    """分页查询数据列表"""
    db     = get_db()
    result = db.list_all_data(dataset_id, status=status, keyword=keyword,
                               page=page, page_size=page_size, enrich=True)
    return success(page_data(result["list"], page, page_size, result["total"]))


@router.get("/stats")
async def get_stats(
    user:       CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """各阶段数据量统计"""
    db = get_db()
    return success(db.stats(dataset_id))


@router.get("/{item_id}")
async def get_data_item(item_id: int, user: CurrentUser):
    """获取数据详情（含标注列表、评论列表、冲突信息）"""
    db   = get_db()
    item = db.get_data(item_id, enrich=True)
    if not item:
        raise NotFoundError(f"数据不存在: id={item_id}")

    # 追加评论和冲突列表
    item["comments"]  = db.list_comments(item_id)
    item["conflicts"] = db.get_open_conflicts(item_id)
    return success(item)


@router.post("/upload")
async def upload_data(
    user:        CurrentUser,
    dataset_id:  int        = Query(..., description="目标数据集 ID"),
    file:        UploadFile  = File(...),
    text_column: str         = Form("text"),
):
    """上传数据文件（xlsx / json / csv），解析后写入指定 dataset"""
    db = get_db()
    if not db.get_dataset(dataset_id):
        raise NotFoundError(f"数据集不存在: {dataset_id}")

    content = await file.read()
    if not content:
        raise ParamError("文件为空")

    try:
        texts = parse_file(file.filename or "", content)
    except Exception as e:
        raise ParamError(f"文件解析失败: {e}")

    created  = 0
    skipped  = 0
    dup_skip = 0
    for text in texts:
        if not is_valid(text):
            skipped += 1
            continue
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        result = db.create_data(
            dataset_id,
            content=text,
            source=ext,
            source_ref=file.filename or "",
            created_by=user.username,
        )
        if result is None:
            dup_skip += 1
        else:
            created += 1

    return success({
        "filename":     file.filename,
        "created":      created,
        "skipped":      skipped,
        "dup_skipped":  dup_skip,
        "total_parsed": len(texts),
    })


@router.delete("/{item_id}")
async def delete_data_item(item_id: int, user: CurrentUser):
    """删除数据条目"""
    db = get_db()
    ok = db.delete_data(item_id)
    if not ok:
        raise NotFoundError(f"数据不存在: id={item_id}")
    return success({"deleted_id": item_id})
