"""
Pipeline API
- 全量运行 / 单步运行（后台异步）
- 查询当前状态（按 dataset 隔离）
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.pipeline.engine import STEPS, run_all, run_step
from datapulse.repository.base import get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class RunStepRequest(BaseModel):
    step: str
    dataset_id: int


@router.post("/run")
async def run_pipeline(
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """触发全量 Pipeline（后台异步执行）"""
    if not user.has_permission("pipeline:run"):
        raise HTTPException(403, "无权限触发 Pipeline")
    db = get_db()
    current = db.get_pipeline_status(dataset_id)
    if current.get("status") == "running":
        raise HTTPException(409, "Pipeline 正在运行，请勿重复触发")
    background_tasks.add_task(run_all, dataset_id)
    return {"success": True, "message": "Pipeline 已启动，在后台运行"}


@router.post("/run-step")
async def run_single_step(body: RunStepRequest, user: CurrentUser):
    """同步运行单个步骤（适合调试）"""
    if not user.has_permission("pipeline:run"):
        raise HTTPException(403, "无权限触发 Pipeline")
    try:
        result = await run_step(body.dataset_id, body.step)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"步骤执行失败: {e}")


@router.get("/status")
async def get_status(
    user: CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """查询指定 dataset 的 Pipeline 状态"""
    db = get_db()
    return {"success": True, "data": db.get_pipeline_status(dataset_id)}


@router.get("/steps")
async def get_steps(user: CurrentUser):
    """返回所有可用步骤名称"""
    return {"success": True, "steps": STEPS}
