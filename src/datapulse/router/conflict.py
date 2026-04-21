"""
冲突检测路由
GET  /api/conflicts               — 分页查询冲突（by dataset_id，支持 status / conflict_type 过滤）
GET  /api/conflicts/by-data       — 按 data_id 查询冲突（不分页）
POST /api/conflicts/detect        — 触发异步冲突检测
POST /api/conflicts/self-check    — 触发高质量数据自检
POST /api/conflicts/batch-resolve — 批量裁决冲突（多选 + 统一标签）
POST /api/conflicts/batch-revoke  — 批量撤销自检冲突（恢复 checked）
PATCH /api/conflicts/{id}/resolve — 单条裁决冲突
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.exceptions import NotFoundError, PipelineRunningError
from datapulse.core.response import page_data, success
from datapulse.modules.conflict import run_conflict_detection, run_quality_self_check
from datapulse.repository.base import get_db

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
_SHANGHAI   = ZoneInfo("Asia/Shanghai")


class ResolveBody(BaseModel):
    label: str
    cot:   str | None = None


class BatchResolveBody(BaseModel):
    conflict_ids: list[int]
    label:        str
    cot:          str | None = None


class BatchRevokeBody(BaseModel):
    conflict_ids: list[int]


# ── 查询 ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_conflicts(
    user:          CurrentUser,
    dataset_id:    int        = Query(...,  description="数据集 ID"),
    status:        str | None = Query(None, description="open / resolved / revoked"),
    conflict_type: str | None = Query(None, description="label_conflict / semantic_conflict"),
    keyword:       str | None = Query(None, description="文本内容关键词过滤（模糊匹配）"),
    page:          int        = Query(1,    ge=1),
    page_size:     int        = Query(10,   ge=1, le=100),
):
    """分页查询指定 dataset 下的冲突列表"""
    db = get_db()
    records, total = db.list_conflicts_by_dataset_paged(
        dataset_id,
        status=status,
        conflict_type=conflict_type,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return success(page_data(records, page, page_size, total))


@router.get("/by-data")
async def list_conflicts_by_data(
    user:    CurrentUser,
    data_id: int = Query(..., description="数据条目 ID"),
):
    """查询单条数据的所有 open 冲突（不分页，供详情面板使用）"""
    db = get_db()
    return success(db.get_open_conflicts(data_id))


# ── 触发检测 ──────────────────────────────────────────────────────────────────

@router.post("/detect")
async def trigger_conflict_detection(
    background_tasks: BackgroundTasks,
    user:             CurrentUser,
    dataset_id:       int = Query(..., description="数据集 ID"),
):
    """触发冲突检测（异步执行）"""
    db = get_db()
    ps = db.get_pipeline_status(dataset_id)
    if ps.get("status") == "running":
        raise PipelineRunningError()

    from datapulse.pipeline.engine import _now, _set_status
    _set_status(dataset_id, "running", "check", 0, started_at=_now(), operator=user.username)
    background_tasks.add_task(_run_check, dataset_id, user.username)

    return success({
        "task_id": str(dataset_id),
        "status":  "running",
        "message": "冲突检测已启动，可通过 GET /api/pipeline/status?dataset_id=X 查询进度",
    })


async def _run_check(dataset_id: int, operator: str) -> None:
    from datapulse.pipeline.engine import _now, _set_status, step_check
    try:
        await step_check(dataset_id, operator=operator)
        _set_status(dataset_id, "completed", "check", 100, finished_at=_now(), operator=operator)
    except Exception as e:
        _set_status(dataset_id, "error", "check", 0, error=str(e), finished_at=_now(), operator=operator)


@router.post("/self-check")
async def trigger_quality_self_check(
    background_tasks: BackgroundTasks,
    user:             CurrentUser,
    dataset_id:       int = Query(..., description="数据集 ID"),
):
    """高质量数据自检（异步执行）"""
    db = get_db()
    ps = db.get_pipeline_status(dataset_id)
    if ps.get("status") == "running":
        raise PipelineRunningError()

    from datapulse.pipeline.engine import _now, _set_status
    _set_status(dataset_id, "running", "self_check", 0, started_at=_now(), operator=user.username)
    background_tasks.add_task(_run_self_check, dataset_id, user.username)

    return success({
        "task_id": str(dataset_id),
        "status":  "running",
        "message": "高质量数据自检已启动，可通过 GET /api/pipeline/status?dataset_id=X 查询进度",
    })


async def _run_self_check(dataset_id: int, operator: str) -> None:
    from datapulse.pipeline.engine import _now, _set_status
    try:
        result = await run_quality_self_check(dataset_id, operator=operator)
        _set_status(dataset_id, "completed", "self_check", 100,
                    detail=result, finished_at=_now(), operator=operator)
    except Exception as e:
        _set_status(dataset_id, "error", "self_check", 0,
                    error=str(e), finished_at=_now(), operator=operator)


# ── 裁决（单条） ──────────────────────────────────────────────────────────────

@router.patch("/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: int, body: ResolveBody, user: CurrentUser):
    """单条裁决冲突：写入 manual 标注结果，推进 stage 到 checked，记录评论。"""
    db       = get_db()
    conflict = db.get_conflict_by_id(conflict_id)
    if not conflict:
        raise NotFoundError(f"冲突记录不存在: id={conflict_id}")
    data_id = conflict["data_id"]

    db.set_annotation_result_manual(data_id, body.label, resolver=user.username, cot=body.cot)
    db.update_stage(data_id, "checked", updated_by=user.username)
    db.resolve_conflict(conflict_id)

    now_str = datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M")
    db.create_comment(
        data_id, user.username,
        f"[裁决] {user.username} 于 {now_str} 解决冲突，最终标注为「{body.label}」",
    )

    return success({
        "conflict_id":  conflict_id,
        "data_id":      data_id,
        "final_label":  body.label,
        "label_source": "manual",
        "resolver":     user.username,
        "status":       "resolved",
    })


# ── 裁决（批量） ──────────────────────────────────────────────────────────────

@router.post("/batch-resolve")
async def batch_resolve_conflicts(body: BatchResolveBody, user: CurrentUser):
    """批量裁决冲突：对所有选中的 open 冲突统一写入同一标签，批量推进 stage。

    适用场景：多条冲突确认正确标签相同时，一键全部解决，无需逐条操作。
    """
    if not body.conflict_ids:
        return success({"resolved": 0, "data_ids": []})

    db = get_db()

    # 取出所有 open 冲突记录，获取对应 data_id
    resolved_ids = []
    data_ids     = []
    for cid in body.conflict_ids:
        conflict = db.get_conflict_by_id(cid)
        if not conflict or conflict["status"] != "open":
            continue
        data_id = conflict["data_id"]
        db.set_annotation_result_manual(data_id, body.label, resolver=user.username, cot=body.cot)
        db.update_stage(data_id, "checked", updated_by=user.username)
        resolved_ids.append(cid)
        data_ids.append(data_id)

    # 批量更新冲突状态
    db.batch_resolve_conflicts(resolved_ids)

    # 批量写评论
    now_str = datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M")
    for data_id in data_ids:
        db.create_comment(
            data_id, user.username,
            f"[批量裁决] {user.username} 于 {now_str} 批量解决冲突，最终标注为「{body.label}」",
        )

    return success({
        "resolved":  len(resolved_ids),
        "data_ids":  data_ids,
        "label":     body.label,
        "resolver":  user.username,
    })


# ── 撤销（批量）──────────────────────────────────────────────────────────────

@router.post("/batch-revoke")
async def batch_revoke_conflicts(body: BatchRevokeBody, user: CurrentUser):
    """批量撤销自检冲突，将数据恢复到 checked stage。

    适用场景：调整相似度阈值后重新自检前，先撤销当前自检结果，
    或者确认自检标记的冲突实为误报，无需裁决。
    撤销后数据重回 checked，不修改标注结果，可随时再次自检。
    """
    if not body.conflict_ids:
        return success({"revoked": 0, "data_ids": []})

    db       = get_db()
    # batch_revoke_conflicts 返回受影响的 data_id 列表
    data_ids = db.batch_revoke_conflicts(body.conflict_ids)

    # 将对应数据恢复到 checked
    for data_id in data_ids:
        db.update_stage(data_id, "checked", updated_by=user.username)

    return success({
        "revoked":  len(data_ids),
        "data_ids": data_ids,
    })
