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

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.config.settings import get_settings
from datapulse.core.exceptions import NotFoundError, ParamError
from datapulse.core.response import page_data, success
from datapulse.modules.eval import eval_worker
from datapulse.modules.eval.bu.registry import get_bu, list_bus
from datapulse.modules.eval.llm.judge_runner import active_backend
from datapulse.pipeline import eval_engine

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]

_ALLOWED = (".xlsx", ".xls")
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _start_task(filename: str, file_path: str, bu: str, operator: str) -> dict:
    task = eval_engine.create_task(filename, file_path, bu, created_by=operator)
    # 入队到独立后台 worker 串行执行，立即返回；不占 web 请求线程池（避免拖垮整站）
    eval_worker.submit(task["task_id"], resume=False, operator=operator)
    return task


@router.post("/upload")
async def upload(
    user: CurrentUser,
    file: UploadFile = File(...),
    bu: str = "securities",
):
    """上传日志 Excel 起评测。bu 指定业务单元（securities/life），决定意图体系。"""
    if not file.filename or not file.filename.lower().endswith(_ALLOWED):
        raise ParamError("只接受 .xlsx / .xls 文件")
    dest = Path(get_settings().eval_uploads_dir) / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    task = _start_task(file.filename, str(dest), get_bu(bu).code, user.username)
    return success(task)


@router.get("/sample")
async def run_sample(
    user: CurrentUser,
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
    task = _start_task(sample.name, str(sample), bu_cfg.code, user.username)
    return success(task)


@router.get("/tasks")
async def list_tasks(
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    bu: str = Query("", description="按业务单元过滤；空则返回全部"),
):
    tasks, total = eval_engine.list_tasks_paged(page, page_size, bu=bu)
    return success(page_data(tasks, page, page_size, total))


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
    q: str = Query("", description="按客户问题关键字过滤"),
    intent: str = Query("", description="按业务分类过滤"),
):
    """分页查逐条评测明细（百万级下替代 /result 附带全量 rows）。

    flag=all（默认）按 row_index 分页，支持 q（问题关键字）/ intent（业务分类）过滤；
    flag=review 只取需复核子集（有限上限）。「不一致」子集前端直接用 result.disagreements。
    """
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if flag == "review":
        rows = eval_engine.list_review_rows(task_id)
        return success(page_data(rows, 1, len(rows), len(rows)))
    rows = eval_engine.list_rows(task_id, page, page_size, q=q, intent=intent)
    total = eval_engine.count_rows(task_id, q=q, intent=intent)
    return success(page_data(rows, page, page_size, total))


class ReviewBody(BaseModel):
    reviewed_dispatch: str = ""   # 是 / 否 / ''(不改)
    reviewed_resolved: str = ""   # 是 / 否 / ''(不改)
    reviewed_intent: str = ""     # 改后的业务分类('' 不改)
    comment: str = ""


@router.put("/tasks/{task_id}/rows/{row_index}/review")
async def submit_review(task_id: str, row_index: int, body: ReviewBody, user: CurrentUser):
    """提交/更新某条明细的人工复核（覆盖 AI 判定，指标按最终值重算）。"""
    if not eval_engine.get_task(task_id):
        raise NotFoundError("任务不存在")
    for field, val in (("reviewed_dispatch", body.reviewed_dispatch),
                       ("reviewed_resolved", body.reviewed_resolved)):
        if val not in ("", "是", "否"):
            raise ParamError(f"{field} 只能是 是 / 否 / 空")
    rec = eval_engine.submit_review(
        task_id, row_index,
        reviewed_dispatch=body.reviewed_dispatch, reviewed_resolved=body.reviewed_resolved,
        reviewed_intent=body.reviewed_intent.strip(), comment=body.comment,
        reviewer=user.username)
    return success(rec)


@router.delete("/tasks/{task_id}/rows/{row_index}/review")
async def delete_review(task_id: str, row_index: int, user: CurrentUser):
    """撤销某条明细的人工复核（该行恢复用 AI 判定，指标随之还原）。"""
    eval_engine.delete_review(task_id, row_index)
    return success({"deleted": True})


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str, user: CurrentUser):
    """断点续跑：对中断的任务，跳过已完成行继续。"""
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if not eval_engine.can_resume(task_id):
        raise ParamError("该任务无需或无法续跑")
    eval_worker.submit(task_id, resume=True, operator=user.username)
    return success(eval_engine.get_task(task_id))


@router.post("/tasks/{task_id}/rerun")
async def rerun_task(task_id: str, user: CurrentUser):
    """重新评测：清空已落盘结果，用当前提示词从头重跑。"""
    if not eval_engine.rerun_task(task_id):
        raise NotFoundError("任务不存在")
    eval_worker.submit(task_id, resume=False, operator=user.username)
    return success(eval_engine.get_task(task_id))


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: CurrentUser):
    """删除评测任务（连逐条结果一起硬删）。"""
    if not eval_engine.delete_task(task_id):
        raise NotFoundError("任务不存在")
    return success({"deleted": True})


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


# ── 提示词管理（页面实时编辑，改后不重启即生效）──────────────────────────────

class PromptSaveBody(BaseModel):
    content: str


@router.get("/prompts")
async def list_prompts(user: CurrentUser, bu: str = "securities"):
    """某 BU 的全部模板槽位（专属/继承通用）+ 跨 BU 共享槽位。"""
    return success(eval_engine.list_prompts(bu))


@router.get("/prompts/{bu}/{name}")
async def get_prompt(bu: str, name: str, user: CurrentUser):
    """单条提示词：当前有效内容 + 文件出厂默认 + 是否自定义。"""
    p = eval_engine.get_prompt(bu, name)
    if not p:
        raise NotFoundError("提示词不存在")
    return success(p)


@router.put("/prompts/{bu}/{name}")
async def save_prompt(bu: str, name: str, body: PromptSaveBody, user: CurrentUser):
    """保存提示词，立即生效（下次评测读到新值，无需重启）。"""
    if not body.content.strip():
        raise ParamError("提示词内容不能为空")
    return success(eval_engine.save_prompt(bu, name, body.content, operator=user.username))


@router.post("/prompts/{bu}/{name}/reset")
async def reset_prompt(bu: str, name: str, user: CurrentUser):
    """重置为文件出厂默认（删除库中自定义）。"""
    eval_engine.reset_prompt(bu, name)
    return success(eval_engine.get_prompt(bu, name))


# ── 业务分类管理（按 BU，页面增删改，改后不重启即生效）────────────────────────

class CategoryBody(BaseModel):
    name: str
    definition: str = ""


@router.get("/categories")
async def list_categories(user: CurrentUser, bu: str = "securities"):
    """列出某 BU 的全部业务分类。"""
    return success({"bu": bu, "categories": eval_engine.list_categories(bu)})


@router.post("/categories")
async def create_category(user: CurrentUser, body: CategoryBody, bu: str = "securities"):
    """新增一个业务分类。"""
    if not body.name.strip():
        raise ParamError("分类名不能为空")
    return success(eval_engine.create_category(bu, body.name.strip(), body.definition, operator=user.username))


@router.put("/categories/{cat_id}")
async def update_category(cat_id: int, body: CategoryBody, user: CurrentUser):
    """更新业务分类名/定义。"""
    if not body.name.strip():
        raise ParamError("分类名不能为空")
    rec = eval_engine.update_category(cat_id, body.name.strip(), body.definition, operator=user.username)
    if not rec:
        raise NotFoundError("分类不存在")
    return success(rec)


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: int, user: CurrentUser):
    """删除业务分类。"""
    if not eval_engine.delete_category(cat_id):
        raise NotFoundError("分类不存在")
    return success({"deleted": True})


# ── 活动标问管理（写死按钮触发的写死回复，评测时整条跳过，不计入指标）────────────

class ActivityBody(BaseModel):
    question: str
    note: str = ""


@router.get("/activity-questions")
async def list_activity_questions(user: CurrentUser, bu: str = "securities"):
    """列出某 BU 的全部活动标问。"""
    return success({"bu": bu, "questions": eval_engine.list_activity_questions(bu)})


@router.post("/activity-questions")
async def create_activity_question(user: CurrentUser, body: ActivityBody, bu: str = "securities"):
    """新增一条活动标问（与客户问题精确相等即命中、整条跳过评测）。已存在则更新备注。"""
    if not body.question.strip():
        raise ParamError("活动标问不能为空")
    return success(eval_engine.create_activity_question(
        bu, body.question.strip(), body.note, operator=user.username))


@router.delete("/activity-questions/{act_id}")
async def delete_activity_question(act_id: int, user: CurrentUser):
    """删除一条活动标问。"""
    if not eval_engine.delete_activity_question(act_id):
        raise NotFoundError("活动标问不存在")
    return success({"deleted": True})


# ── 规则短路管理（命中写死结果、免 LLM 调用，计入指标）────────────────────────

class RuleBody(BaseModel):
    question: str
    expected_answer: str = ""
    judge_json: dict          # 完整 judge 输出（11 字段，结构同 LLM output）
    note: str = ""


@router.get("/rules")
async def list_rules(user: CurrentUser, bu: str = "securities"):
    """列出某 BU 的全部短路规则。"""
    return success({"bu": bu, "rules": eval_engine.list_rules(bu)})


@router.post("/rules")
async def upsert_rule(user: CurrentUser, body: RuleBody, bu: str = "securities"):
    """新增/更新一条短路规则（按 (bu, question) upsert）。"""
    if not body.question.strip():
        raise ParamError("触发问题不能为空")
    if not isinstance(body.judge_json, dict) or not body.judge_json:
        raise ParamError("judge_json 不能为空")
    return success(eval_engine.upsert_rule(
        bu, body.question.strip(), body.expected_answer, body.judge_json,
        note=body.note, operator=user.username))


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, user: CurrentUser):
    """删除一条短路规则。"""
    if not eval_engine.delete_rule(rule_id):
        raise NotFoundError("规则不存在")
    return success({"deleted": True})
