"""
Pipeline API
- 全量运行 / 单步运行（后台异步）
- 查询当前状态（按 dataset 隔离）
- 重置 Pipeline 状态（解除卡住 / 错误状态）
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.pipeline.engine import STEPS, run_all_sync, run_embed_job_sync, run_step
from datapulse.repository.base import get_db

_SHANGHAI = ZoneInfo("Asia/Shanghai")

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
    # run_all_sync 是 sync 函数，BackgroundTasks 会自动放到线程池执行，
    # 不会阻塞主 asyncio 事件循环（async 函数会直接在事件循环内 await，会卡住）
    background_tasks.add_task(run_all_sync, dataset_id, user.username)
    return {"success": True, "message": "Pipeline 已启动，在后台运行"}


@router.post("/run-step")
async def run_single_step(body: RunStepRequest, user: CurrentUser):
    """同步运行单个步骤（适合调试）"""
    if not user.has_permission("pipeline:run"):
        raise HTTPException(403, "无权限触发 Pipeline")
    try:
        result = await run_step(body.dataset_id, body.step, operator=user.username)
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


@router.post("/embed")
async def run_embed(
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """
    触发 Embedding 离线任务（后台异步执行，不阻塞主 Pipeline）。

    embedding 推理 + FAISS 索引重建是 CPU/GPU 密集型操作，已从主流程解耦。
    任务状态通过 GET /pipeline/status 的 embed_job 字段查询。
    """
    if not user.has_permission("pipeline:run"):
        raise HTTPException(403, "无权限触发 Embed Job")
    db      = get_db()
    current = db.get_pipeline_status(dataset_id) or {}
    embed   = current.get("embed_job", {})
    if embed.get("status") == "running":
        raise HTTPException(409, "Embed Job 正在运行，请勿重复触发")
    background_tasks.add_task(run_embed_job_sync, dataset_id, user.username)
    return {"success": True, "message": "Embed Job 已启动，在后台运行"}


@router.post("/reset")
async def reset_pipeline(
    user: CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
    reset_embed: bool = Query(False, description="同时重置 embed_job 状态"),
):
    """
    重置指定 dataset 的 Pipeline 状态为 idle。

    适用场景：
      - Pipeline 因异常卡在 running 状态，实际已不在运行
      - 需要重新触发全量 Pipeline，但旧状态阻止了 /run 的防重复校验
      - embed_job 失败后需要清除错误状态重新触发

    注意：此操作不修改数据本身（t_data_item / t_data_state），仅重置状态记录。
    """
    if not user.has_permission("pipeline:run"):
        raise HTTPException(403, "无权限重置 Pipeline 状态")
    db      = get_db()
    current = db.get_pipeline_status(dataset_id) or {}

    # 保留 embed_job 字段（除非明确要求重置）
    embed_job = {} if reset_embed else current.get("embed_job", {})

    db.set_pipeline_status(dataset_id, {
        "status":       "idle",
        "current_step": "",
        "progress":     0,
        "detail":       {},
        "results":      [],
        "error":        None,
        "embed_job":    embed_job,
        "updated_at":   datetime.now(_SHANGHAI),
        "updated_by":   user.username,
    })
    return {"success": True, "message": "Pipeline 状态已重置为 idle"}


@router.get("/steps")
async def get_steps(user: CurrentUser):
    """返回所有可用步骤名称"""
    return {"success": True, "steps": STEPS}
