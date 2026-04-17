"""
数据管理路由
GET  /api/data-items          — 分页列表（支持 keyword / status 过滤）
GET  /api/data-items/{id}     — 详情（含标注、评论、冲突）
POST /api/data-items/upload   — 文件上传
DELETE /api/data-items/{id}   — 删除
GET  /api/data-items/stats    — 各阶段统计
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import NotFoundError, ParamError
from datapulse.core.response import page_data, success
from datapulse.modules.processing import is_valid, parse_file, parse_file_rows
from datapulse.repository.base import get_db

router     = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class CreateDataItemBody(BaseModel):
    dataset_id: int
    content:    str
    source_ref: str = ""


class BatchDeleteBody(BaseModel):
    ids: list[int]


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
    label:      str | None    = Query(None, description="按标注标签过滤"),
    start_date: str | None    = Query(None, description="更新时间起（YYYY-MM-DD）"),
    end_date:   str | None    = Query(None, description="更新时间止（YYYY-MM-DD）"),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(20, ge=1, le=200),
):
    """分页查询数据列表"""
    db     = get_db()
    result = db.list_all_data(
        dataset_id, status=status, keyword=keyword, label=label,
        start_date=start_date, end_date=end_date,
        page=page, page_size=page_size, enrich=True,
    )
    return success(page_data(result["list"], page, page_size, result["total"]))


@router.get("/stats")
async def get_stats(
    user:       CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """各阶段数据量统计"""
    db = get_db()
    return success(db.stats(dataset_id))


@router.get("/label-options")
async def get_label_options(
    user:       CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """返回该 dataset 中所有已使用的标注标签（用于前端动态下拉过滤）"""
    db = get_db()
    labels = db.get_distinct_labels(dataset_id)
    return success(labels)


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
    user:         CurrentUser,
    dataset_id:   int        = Query(..., description="目标数据集 ID"),
    file:         UploadFile  = File(...),
    text_column:  str         = Form("text"),
    label_column: str         = Form("label"),
):
    """上传数据文件（xlsx / json / csv），解析后批量写入指定 dataset。

    自动检测 label 列：
      - 文件含 label（或等价列）→ 带标注上传模式：同时写入 t_pre_annotation，
        状态直接推进到 pre_annotated，score=1，cot 为迁移说明。
      - 文件无 label 列 → 原始上传模式：写入 raw 状态，等待 pipeline 处理。

    性能说明：
      - 文件解析（pd.read_excel 等）是 CPU 密集型，通过 run_in_executor 放到线程池，
        避免阻塞 asyncio 事件循环；
      - 数据库写入使用单事务批量 INSERT，不逐行开关事务。
    """
    db = get_db()
    if not db.get_dataset(dataset_id):
        raise NotFoundError(f"数据集不存在: {dataset_id}")

    content = await file.read()
    if not content:
        raise ParamError("文件为空")

    filename = file.filename or ""
    ext      = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # ── 文件解析：CPU 密集，放线程池避免阻塞事件循环 ─────────────────────────
    loop = asyncio.get_event_loop()
    try:
        rows: list[dict] = await loop.run_in_executor(
            None, partial(parse_file_rows, filename, content, text_column, label_column)
        )
    except Exception as e:
        raise ParamError(f"文件解析失败: {e}")

    # ── 过滤无效文本 ──────────────────────────────────────────────────────────
    total_parsed = len(rows)
    valid_rows   = [r for r in rows if is_valid(r["content"])]
    invalid_skip = total_parsed - len(valid_rows)

    if not valid_rows:
        return success({
            "filename":       filename,
            "created":        0,
            "skipped":        invalid_skip,
            "dup_skipped":    0,
            "pre_annotated":  0,
            "total_parsed":   total_parsed,
        })

    # ── 批量写入：单事务，放线程池避免阻塞事件循环 ────────────────────────────
    result: dict[str, int] = await loop.run_in_executor(
        None,
        partial(
            db.bulk_create_data_with_labels,
            dataset_id, valid_rows, ext, filename, user.username,
        ),
    )

    return success({
        "filename":       filename,
        "created":        result["created"],
        "skipped":        invalid_skip,
        "dup_skipped":    result["skipped"],
        "annotated":      result.get("annotated", 0),
        "total_parsed":   total_parsed,
    })


@router.post("/batch-delete")
async def batch_delete_data_items(body: BatchDeleteBody, user: CurrentUser):
    """批量删除数据条目"""
    if not body.ids:
        raise ParamError("ids 不能为空")
    db = get_db()
    deleted = db.batch_delete_data(body.ids)
    return success({"deleted_count": deleted, "ids": body.ids})


@router.delete("/{item_id}")
async def delete_data_item(item_id: int, user: CurrentUser):
    """删除数据条目"""
    db = get_db()
    ok = db.delete_data(item_id)
    if not ok:
        raise NotFoundError(f"数据不存在: id={item_id}")
    return success({"deleted_id": item_id})
