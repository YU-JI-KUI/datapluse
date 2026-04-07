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

_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(_SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user
from storage.nas import get_nas

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


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
    """
    获取待标注队列：pre_annotated 状态的数据
    前端标注页面使用
    """
    nas = get_nas()
    result = nas.list_all(status="pre_annotated", page=page, page_size=page_size)
    return {"success": True, **result}


@router.get("/next")
async def get_next(user: CurrentUser):
    """获取下一条待标注数据（翻牌式）"""
    nas = get_nas()
    items = nas.list_by_status("pre_annotated")
    if not items:
        return {"success": True, "data": None, "message": "标注队列已清空"}
    # 取最早创建的一条
    item = min(items, key=lambda x: x.get("created_at", ""))
    # 标记为 labeling
    item["status"] = "labeling"
    nas.update(item)
    return {"success": True, "data": item}


@router.post("/submit")
async def submit(body: AnnotationSubmit, user: CurrentUser):
    """提交单条标注结果"""
    nas = get_nas()
    item = nas.get(body.item_id)
    if not item:
        raise HTTPException(404, f"未找到 id={body.item_id}")

    item["label"] = body.label
    item["annotator"] = body.annotator or user.username
    item["annotated_at"] = _now()
    item["status"] = "labeled"
    nas.update(item)

    return {"success": True, "data": item}


@router.post("/batch-submit")
async def batch_submit(body: BatchAnnotationSubmit, user: CurrentUser):
    """批量提交标注（用于快速标注场景）"""
    nas = get_nas()
    results = []
    errors = []
    for ann in body.annotations:
        item = nas.get(ann.item_id)
        if not item:
            errors.append({"item_id": ann.item_id, "error": "不存在"})
            continue
        item["label"] = ann.label
        item["annotator"] = ann.annotator or user.username
        item["annotated_at"] = _now()
        item["status"] = "labeled"
        nas.update(item)
        results.append(item["id"])

    return {"success": True, "updated": results, "errors": errors}


@router.get("/labeled")
async def get_labeled(
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查看已标注数据"""
    nas = get_nas()
    result = nas.list_all(status="labeled", page=page, page_size=page_size)
    return {"success": True, **result}
