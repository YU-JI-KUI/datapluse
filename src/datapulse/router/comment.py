"""
评论系统路由
POST /api/comments     — 添加评论
GET  /api/comments     — 查询评论（by data_id）
DELETE /api/comments/{id} — 删除评论（本人才能删）
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import ForbiddenError, NotFoundError
from datapulse.core.response import success
from datapulse.repository.base import get_db
from datapulse.schemas.annotation import CommentCreate

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


@router.post("")
async def add_comment(body: CommentCreate, user: CurrentUser):
    """添加评论"""
    db   = get_db()
    item = db.get_data(body.data_id, enrich=False)
    if not item:
        raise NotFoundError(f"数据不存在: id={body.data_id}")
    comment = db.create_comment(body.data_id, user.username, body.comment)
    return success(comment)


@router.get("")
async def list_comments(
    user:    CurrentUser,
    data_id: int = Query(..., description="数据 ID"),
):
    """获取某条数据的所有评论"""
    db = get_db()
    return success(db.list_comments(data_id))
