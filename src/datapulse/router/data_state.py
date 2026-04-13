"""
数据状态流转路由
PATCH /api/data-state  — 手动更新数据阶段
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import NotFoundError, ParamError
from datapulse.core.response import success
from datapulse.repository.base import get_db
from datapulse.schemas.annotation import DataStateUpdate

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]

_VALID_STAGES = {"raw", "cleaned", "pre_annotated", "annotated", "checked"}


@router.patch("")
async def update_data_state(body: DataStateUpdate, user: CurrentUser):
    """手动更新数据流转阶段（管理员或 pipeline 内部使用）"""
    if body.stage not in _VALID_STAGES:
        raise ParamError(f"无效的 stage: {body.stage}，可选: {sorted(_VALID_STAGES)}")

    db   = get_db()
    item = db.get_data(body.data_id, enrich=False)
    if not item:
        raise NotFoundError(f"数据不存在: id={body.data_id}")

    db.update_stage(body.data_id, body.stage, updated_by=user.username)
    return success({"data_id": body.data_id, "stage": body.stage})
