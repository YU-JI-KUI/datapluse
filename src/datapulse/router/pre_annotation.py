"""
LLM 预标注路由
POST /api/pre-annotations/run  — 触发预标注（异步，返回 task_id）
GET  /api/pre-annotations      — 查询某数据的预标注历史
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import PipelineRunningError
from datapulse.core.response import success
from datapulse.repository.base import get_db

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


@router.post("/run")
async def run_pre_annotation(
    background_tasks: BackgroundTasks,
    user:             CurrentUser,
    dataset_id:       int = Query(..., description="数据集 ID"),
):
    """
    触发 LLM 预标注（异步）
    针对所有 cleaned 状态的数据，批量调用 LLM 预测并写入 t_pre_annotation
    """
    db = get_db()
    ps = db.get_pipeline_status(dataset_id)
    if ps.get("status") == "running":
        raise PipelineRunningError()

    from datapulse.pipeline.engine import _set_status, _now
    _set_status(dataset_id, "running", "pre_annotate", 0, started_at=_now())
    background_tasks.add_task(_run_pre_annotate, dataset_id, user.username)

    return success({
        "task_id": str(dataset_id),
        "status":  "running",
        "message": "预标注已启动，可通过 GET /api/pipeline/status?dataset_id=X 查询进度",
    })


async def _run_pre_annotate(dataset_id: int, operator: str) -> None:
    from datapulse.pipeline.engine import step_pre_annotate, _set_status, _now
    try:
        result = await step_pre_annotate(dataset_id)
        _set_status(dataset_id, "completed", "pre_annotate", 100,
                    finished_at=_now(), results=result)
    except Exception as e:
        _set_status(dataset_id, "error", "pre_annotate", 0,
                    error=str(e), finished_at=_now())


@router.get("")
async def list_pre_annotations(
    user:    CurrentUser,
    data_id: int = Query(..., description="数据 ID"),
):
    """查询某条数据的预标注历史"""
    db = get_db()
    return success(db.get_latest_pre_annotation(data_id))
