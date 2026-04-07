"""
标注 API
- 获取待标注列表
- 提交标注结果
- 获取下一条（用于翻牌式标注）
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user
from storage.db import get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]

_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(_SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


class AnnotationSubmit(BaseModel):
    item_id: str
    label: str
    annotator: Optional[str] = None


class BatchAnnotationSubmit(BaseModel):
    annotations: list[AnnotationSubmit]


@router.get("/queue")
async def get_queue(
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取待标注队列：pre_annotated 状态的数据"""
    db = get_db()
    result = db.list_all(status="pre_annotated", page=page, page_size=page_size)
    return {"success": True, **result}


@router.get("/next")
async def get_next(user: CurrentUser):
    """获取下一条待标注数据（翻牌式）"""
    db = get_db()
    items = db.list_by_status("pre_annotated")
    if not items:
        return {"success": True, "data": None, "message": "标注队列已清空"}
    item = min(items, key=lambda x: x.get("created_at", ""))
    item["status"] = "labeling"
    db.update(item)
    return {"success": True, "data": item}


@router.post("/submit")
async def submit(body: AnnotationSubmit, user: CurrentUser):
    """提交单条标注结果"""
    db = get_db()
    item = db.get(body.item_id)
    if not item:
        raise HTTPException(404, f"未找到 id={body.item_id}")

    item["label"] = body.label
    item["annotator"] = body.annotator or user.username
    item["annotated_at"] = _now()
    item["status"] = "labeled"
    db.update(item)
    return {"success": True, "data": item}


@router.post("/batch-submit")
async def batch_submit(body: BatchAnnotationSubmit, user: CurrentUser):
    """批量提交标注"""
    db = get_db()
    results = []
    errors = []
    for ann in body.annotations:
        item = db.get(ann.item_id)
        if not item:
            errors.append({"item_id": ann.item_id, "error": "不存在"})
            continue
        item["label"] = ann.label
        item["annotator"] = ann.annotator or user.username
        item["annotated_at"] = _now()
        item["status"] = "labeled"
        db.update(item)
        results.append(item["id"])
    return {"success": True, "updated": results, "errors": errors}


@router.get("/labeled")
async def get_labeled(
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取已标注数据列表"""
    db = get_db()
    result = db.list_all(status="labeled", page=page, page_size=page_size)
    return {"success": True, **result}
