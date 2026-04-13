"""
冲突检测路由
GET  /api/conflicts               — 查询冲突（by data_id 或 dataset_id）
POST /api/conflicts/detect        — 触发异步冲突检测（返回 task_id）
PATCH /api/conflicts/{id}/resolve — 裁决冲突：指定最终标签，写入权威标注并自动评论
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import NotFoundError, PipelineRunningError
from datapulse.core.response import success
from datapulse.modules.conflict import run_conflict_detection
from datapulse.repository.base import get_db

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
_SHANGHAI   = ZoneInfo("Asia/Shanghai")


class ResolveBody(BaseModel):
    label: str   # 裁决后的最终标注标签


@router.get("")
async def list_conflicts(
    user:          CurrentUser,
    data_id:       int | None  = Query(None, description="按数据 ID 查询"),
    dataset_id:    int | None  = Query(None, description="按数据集 ID 查询"),
    status:        str | None  = Query(None, description="open / resolved"),
):
    """查询冲突列表"""
    db = get_db()
    if data_id is not None:
        data = db.get_open_conflicts(data_id)
    elif dataset_id is not None:
        data = db.list_conflicts_by_dataset(dataset_id, status=status)
    else:
        return success([])
    return success(data)


@router.post("/detect")
async def trigger_conflict_detection(
    background_tasks: BackgroundTasks,
    user:             CurrentUser,
    dataset_id:       int = Query(..., description="数据集 ID"),
):
    """
    触发冲突检测（异步执行）
    返回 task_id（= pipeline status 的 dataset_id，可用 GET /api/pipeline/status 查询）
    """
    db = get_db()
    ps = db.get_pipeline_status(dataset_id)
    if ps.get("status") == "running":
        raise PipelineRunningError()

    # 利用已有的 pipeline_status 记录进度
    from datapulse.pipeline.engine import _set_status, _now
    _set_status(dataset_id, "running", "check", 0, started_at=_now())
    background_tasks.add_task(_run_check, dataset_id, user.username)

    return success({
        "task_id": str(dataset_id),
        "status":  "running",
        "message": "冲突检测已启动，可通过 GET /api/pipeline/status?dataset_id=X 查询进度",
    })


async def _run_check(dataset_id: int, operator: str) -> None:
    from datapulse.pipeline.engine import step_check, _set_status, _now
    try:
        await step_check(dataset_id)
        _set_status(dataset_id, "completed", "check", 100, finished_at=_now())
    except Exception as e:
        _set_status(dataset_id, "error", "check", 0, error=str(e), finished_at=_now())


@router.patch("/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: int, body: ResolveBody, user: CurrentUser):
    """裁决冲突：
    1. 直接设置 t_annotation_result.final_label（来源 manual）—— 不修改标注事实
    2. 将数据状态推进到 checked
    3. 标记冲突为已解决
    4. 自动添加裁决日志评论
    """
    db = get_db()

    # 找到冲突记录，获取 data_id
    conflict = db.get_conflict_by_id(conflict_id)
    if not conflict:
        raise NotFoundError(f"冲突记录不存在: id={conflict_id}")
    data_id = conflict["data_id"]

    # 1. 写入最终标注结果（仅更新 t_annotation_result，不改动 t_annotation 事实）
    db.set_annotation_result_manual(data_id, body.label, resolver=user.username)

    # 2. 状态推进到 checked
    db.update_stage(data_id, "checked", updated_by=user.username)

    # 3. 标记冲突已解决
    db.resolve_conflict(conflict_id)

    # 4. 自动评论记录裁决过程
    now_str = datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M")
    db.create_comment(
        data_id,
        user.username,
        f"[裁决] {user.username} 于 {now_str} 解决冲突，最终标注为「{body.label}」",
    )

    return success({
        "conflict_id": conflict_id,
        "data_id":     data_id,
        "final_label": body.label,
        "label_source": "manual",
        "resolver":    user.username,
        "status":      "resolved",
    })
