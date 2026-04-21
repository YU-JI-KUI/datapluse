"""
标注系统路由
POST   /api/annotations          — 提交标注（自动版本管理 + 自动评论）
GET    /api/annotations          — 获取标注列表（by data_id）
DELETE /api/annotations          — 撤销当前用户的有效标注
GET    /api/annotations/queue    — 待标注队列（当前用户尚未标注的条目，多人模式）
GET    /api/annotations/next     — 获取下一条待标注数据
POST   /api/annotations/batch    — 批量提交标注
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import NotFoundError
from datapulse.core.response import page_data, success
from datapulse.repository.base import get_db
from datapulse.schemas.annotation import AnnotationCreate

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
_SHANGHAI   = ZoneInfo("Asia/Shanghai")


@router.post("")
async def submit_annotation(body: AnnotationCreate, user: CurrentUser):
    """提交标注结果（自动处理版本递增；同一用户修改时老版本变为历史；自动添加标注日志评论）"""
    db   = get_db()
    item = db.get_data(body.data_id, enrich=False)
    if not item:
        raise NotFoundError(f"数据不存在: id={body.data_id}")

    ann = db.create_annotation(
        data_id=body.data_id,
        username=user.username,
        label=body.label,
        cot=body.cot,
        created_by=user.username,
    )
    # 将数据状态推进到 annotated
    db.update_stage(body.data_id, "annotated", updated_by=user.username)

    # 自动记录标注日志评论（方便在评论区追溯谁在什么时候标注了什么）
    now_str = datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M")
    db.create_comment(
        body.data_id,
        user.username,
        f"[标注] {user.username} 于 {now_str} 标注为「{body.label}」（v{ann['version']}）",
    )

    return success(ann)


@router.delete("")
async def revoke_annotation(
    user:    CurrentUser,
    data_id: int = Query(..., description="数据 ID"),
):
    """撤销当前用户对指定数据的有效标注。
    若该数据已无任何有效标注，状态自动回滚到 pre_annotated，重新进入待标注队列。
    同时记录撤销日志评论。
    """
    db = get_db()
    ok = db.revoke_user_annotation(data_id, user.username)
    if not ok:
        raise NotFoundError("没有找到可撤销的标注，请确认您已对该数据进行过标注")

    # 自动记录撤销日志评论
    now_str = datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M")
    db.create_comment(
        data_id,
        user.username,
        f"[撤销] {user.username} 于 {now_str} 撤销了标注",
    )

    return success({"revoked": True, "data_id": data_id})


@router.get("")
async def list_annotations(
    user:    CurrentUser,
    data_id: int = Query(..., description="数据 ID"),
):
    """获取某条数据的所有有效标注"""
    db = get_db()
    return success(db.get_active_annotations(data_id))


@router.get("/history")
async def get_annotation_history(
    user:     CurrentUser,
    data_id:  int           = Query(..., description="数据 ID"),
    username: str | None    = Query(None, description="过滤标注人"),
):
    """获取标注历史（含已被覆盖的旧版本）"""
    db = get_db()
    return success(db.get_annotation_history(data_id, username))


@router.get("/my-items")
async def get_my_annotation_items(
    user:       CurrentUser,
    dataset_id: int           = Query(..., description="数据集 ID"),
    view:       str           = Query("all", description="all | unannotated | my_annotated"),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(50, ge=1, le=200),
    keyword:    str | None    = Query(None, description="文本关键词过滤"),
    label:      str | None    = Query(None, description="标签过滤（仅 my_annotated 视图生效）"),
):
    """标注工作台统一接口：返回当前用户可操作的所有条目，含 my_annotation 字段。

    view=all          — 全部条目（待标注 + 已标注）
    view=unannotated  — 当前用户尚未标注的条目
    view=my_annotated — 当前用户已标注的条目（按标注时间倒序）
    label             — 按标注标签过滤，仅对 my_annotated 视图有效
    """
    db     = get_db()
    result = db.list_annotatable_for_user(
        dataset_id, user.username, view=view,
        page=page, page_size=page_size, keyword=keyword, label=label,
    )
    from datapulse.core.response import page_data
    return success(page_data(result["list"], page, page_size, result["total"]))


@router.get("/queue")
async def get_annotation_queue(
    user:       CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
    page:       int = Query(1, ge=1),
    page_size:  int = Query(20, ge=1, le=100),
):
    """获取当前用户的待标注队列（多人标注模式）。
    返回状态为 pre_annotated 或 annotated、但当前用户尚未标注的所有条目。
    不同用户看到的是各自独立的待标注队列，互不干扰。
    """
    db     = get_db()
    result = db.list_unannotated_by_user(dataset_id, user.username, page, page_size)
    return success(page_data(result["list"], page, page_size, result["total"]))


@router.get("/next")
async def get_next_item(
    user:       CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """获取下一条待标注数据（按创建时间最早）"""
    db    = get_db()
    items = db.list_data_by_status(dataset_id, "pre_annotated", enrich=True)
    if not items:
        return success(None, message="标注队列已清空")
    item  = min(items, key=lambda x: x.get("created_at") or "")
    return success(item)


@router.post("/batch")
async def batch_submit(
    body: list[AnnotationCreate],
    user: CurrentUser,
):
    """批量提交标注"""
    db      = get_db()
    results = []
    errors  = []
    for req in body:
        item = db.get_data(req.data_id, enrich=False)
        if not item:
            errors.append({"data_id": req.data_id, "error": "数据不存在"})
            continue
        ann = db.create_annotation(req.data_id, user.username, req.label,
                                    cot=req.cot, created_by=user.username)
        db.update_stage(req.data_id, "annotated", updated_by=user.username)
        results.append(ann)
    return success({"updated": results, "errors": errors})
