"""
数据管理 API
- 上传文件（Excel / JSON / CSV），写入指定 dataset
- 列表查询（分页 + 状态过滤）
- 单条查询 / 删除
- 统计信息
所有操作都必须携带 dataset_id query 参数。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.modules.processing import is_valid, parse_file
from datapulse.repository.base import get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


@router.post("/upload")
async def upload(
    user: CurrentUser,
    dataset_id: int = Query(..., description="目标数据集 ID"),
    file: UploadFile = File(...),
    text_column: str = Form("text"),
):
    """上传数据文件，解析后写入指定 dataset 的 raw 状态"""
    db = get_db()
    if not db.get_dataset(dataset_id):
        raise HTTPException(404, f"数据集不存在: {dataset_id}")

    content = await file.read()
    if not content:
        raise HTTPException(400, "文件为空")

    try:
        texts = parse_file(file.filename or "", content)
    except Exception as e:
        raise HTTPException(400, f"文件解析失败: {e}")

    created = 0
    skipped = 0
    for text in texts:
        if not is_valid(text):
            skipped += 1
            continue
        db.create_data(dataset_id, text, source_file=file.filename or "")
        created += 1

    return {
        "success": True,
        "filename": file.filename,
        "created": created,
        "skipped": skipped,
        "total_parsed": len(texts),
    }


@router.get("/list")
async def list_data(
    user: CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """分页查询数据列表"""
    db = get_db()
    result = db.list_all_data(dataset_id, status=status, page=page, page_size=page_size)
    return {"success": True, **result}


@router.get("/stats")
async def stats(
    user: CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """各阶段数据量统计"""
    db = get_db()
    return {"success": True, "data": db.stats(dataset_id)}


@router.get("/{item_id}")
async def get_item(item_id: int, user: CurrentUser):
    db = get_db()
    item = db.get_data(item_id)
    if not item:
        raise HTTPException(404, f"未找到 id={item_id}")
    return {"success": True, "data": item}


@router.delete("/{item_id}")
async def delete_item(item_id: int, user: CurrentUser):
    db = get_db()
    ok = db.delete_data(item_id)
    if not ok:
        raise HTTPException(404, f"未找到 id={item_id}")
    return {"success": True, "message": f"已删除 {item_id}"}
