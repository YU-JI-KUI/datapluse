"""AI 对话评测路由

POST /api/eval/upload              上传 Excel，创建并启动评测任务
GET  /api/eval/sample              用内置样例数据创建并启动评测任务（零配置体验）
GET  /api/eval/tasks               任务列表（分页）
GET  /api/eval/tasks/{id}          任务状态（轮询进度）
GET  /api/eval/tasks/{id}/result   完整评测结果
POST /api/eval/tasks/{id}/resume   断点续跑
GET  /api/eval/tasks/{id}/export        导出不一致 case Excel
GET  /api/eval/tasks/{id}/export/rows   导出逐条明细 Excel
GET  /api/eval/tasks/{id}/export/report 导出完整评估报告 Excel
GET  /api/eval/meta/bus            可选业务单元（BU）
GET  /api/eval/meta/intents        指定 BU 的意图体系
GET  /api/eval/meta/config         当前后端配置（mock / pingan）
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.config.settings import get_settings
from datapulse.core.exceptions import NotFoundError, ParamError
from datapulse.core.response import page_data, success
from datapulse.modules.eval.bu.registry import get_bu, list_bus
from datapulse.modules.eval.llm.judge_runner import active_backend
from datapulse.pipeline import eval_engine

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]

_ALLOWED = (".xlsx", ".xls")
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _start_task(filename: str, file_path: str, bu: str, background_tasks: BackgroundTasks,
                operator: str) -> dict:
    task = eval_engine.create_task(filename, file_path, bu, created_by=operator)
    # 后台异步跑，立刻返回 task_id 供前端轮询（sync 入口由 BackgroundTasks 放到线程池）
    background_tasks.add_task(eval_engine.run_eval_sync, task["task_id"], False, operator)
    return task


@router.post("/upload")
async def upload(
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    bu: str = "securities",
):
    """上传日志 Excel 起评测。bu 指定业务单元（securities/life），决定意图体系。"""
    if not file.filename or not file.filename.lower().endswith(_ALLOWED):
        raise ParamError("只接受 .xlsx / .xls 文件")
    dest = Path(get_settings().eval_uploads_dir) / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    task = _start_task(file.filename, str(dest), get_bu(bu).code, background_tasks, user.username)
    return success(task)


@router.get("/sample")
async def run_sample(
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    bu: str = "securities",
    kind: str = "calib",
):
    """用内置样例数据起一个评测任务，零配置体验全流程。

    bu:   securities（证券）/ life（寿险）
    kind: calib（校准集，有金标）/ prod（生产集，无金标）
    """
    bu_cfg = get_bu(bu)
    fname = bu_cfg.sample_prod if kind == "prod" else bu_cfg.sample_calib
    sample = Path(get_settings().eval_sample_dir) / fname
    if not sample.exists():
        raise NotFoundError(f"{bu_cfg.name} 的样例 {fname} 不存在")
    task = _start_task(sample.name, str(sample), bu_cfg.code, background_tasks, user.username)
    return success(task)


@router.get("/tasks")
async def list_tasks(
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
):
    tasks = eval_engine.list_tasks()
    total = len(tasks)
    start = (page - 1) * page_size
    return success(page_data(tasks[start:start + page_size], page, page_size, total))


@router.get("/tasks/{task_id}")
async def task_status(task_id: str, user: CurrentUser):
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    task["can_resume"] = eval_engine.can_resume(task_id)
    return success(task)


@router.get("/tasks/{task_id}/result")
async def task_result(task_id: str, user: CurrentUser):
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if task["status"] != "done":
        raise ParamError(f"任务尚未完成（当前状态: {task['status']}）")
    result = eval_engine.get_result(task_id)
    if not result:
        raise ParamError("结果尚未就绪")
    return success(result)


@router.get("/tasks/{task_id}/rows")
async def task_rows(
    task_id: str,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    flag: str = Query("all"),
):
    """分页查逐条评测明细（百万级下替代 /result 附带全量 rows）。

    flag=all（默认）按 row_index 分页全量；flag=review 只取需复核子集（有限上限）。
    「不一致」子集前端直接用 result.disagreements，不走此接口。
    """
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if flag == "review":
        rows = eval_engine.list_review_rows(task_id)
        return success(page_data(rows, 1, len(rows), len(rows)))
    rows = eval_engine.list_rows(task_id, page, page_size)
    total = eval_engine.count_rows(task_id)
    return success(page_data(rows, page, page_size, total))


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str, user: CurrentUser, background_tasks: BackgroundTasks):
    """断点续跑：对中断的任务，跳过已完成行继续。"""
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if not eval_engine.can_resume(task_id):
        raise ParamError("该任务无需或无法续跑")
    background_tasks.add_task(eval_engine.run_eval_sync, task_id, True, user.username)
    return success(eval_engine.get_task(task_id))


@router.get("/tasks/{task_id}/export")
async def export_disagreements(task_id: str, user: CurrentUser):
    path = eval_engine.export_disagreements(task_id)
    if not path:
        raise NotFoundError("无可导出结果")
    return FileResponse(path, media_type=_XLSX_MIME, filename=path.name)


@router.get("/tasks/{task_id}/export/rows")
async def export_rows(task_id: str, user: CurrentUser):
    """逐条评测明细全量导出（两种模式都可用）。"""
    path = eval_engine.export_rows(task_id)
    if not path:
        raise NotFoundError("无可导出结果")
    return FileResponse(path, media_type=_XLSX_MIME, filename=path.name)


@router.get("/tasks/{task_id}/export/report")
async def export_report(task_id: str, user: CurrentUser):
    """完整评估报告导出（概览/分发漏斗/洞察/建议 多 sheet）。"""
    path = eval_engine.export_report(task_id)
    if not path:
        raise NotFoundError("无可导出结果")
    return FileResponse(path, media_type=_XLSX_MIME, filename=path.name)


@router.get("/meta/bus")
async def get_bus(user: CurrentUser):
    """列出可选业务单元（BU），供前端上传时选择。"""
    return success({"bus": list_bus()})


@router.get("/meta/intents")
async def get_intents(user: CurrentUser, bu: str = "securities"):
    """返回指定 BU 的意图体系全集。"""
    return success({"bu": get_bu(bu).code, "intents": get_bu(bu).intent_list()})


@router.get("/meta/config")
async def get_config(user: CurrentUser):
    settings = get_settings()
    return success({
        "app_name":           settings.app_name,
        "configured_backend": settings.judge_backend,
        "active_backend":     active_backend(),
        "pingan_ready":       settings.pingan_ready(),
        "concurrency":        settings.judge_concurrency,
    })
