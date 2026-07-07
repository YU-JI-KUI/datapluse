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

from datapulse.router.auth import UserInfo, require_perm
from datapulse.config.settings import get_settings
from datapulse.core.exceptions import NotFoundError, ParamError
from datapulse.core.response import page_data, success
from datapulse.modules.eval import eval_worker
from datapulse.modules.eval.bu.registry import get_bu, list_bus
from datapulse.modules.eval.llm.judge_runner import active_backend
from datapulse.pipeline import eval_engine

router    = APIRouter()
EvalRead  = Annotated[UserInfo, Depends(require_perm("eval:read"))]
EvalWrite = Annotated[UserInfo, Depends(require_perm("eval:write"))]

_ALLOWED = (".xlsx", ".xls")
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _start_task(filename: str, file_path: str, bu: str, operator: str) -> dict:
    task = eval_engine.create_task(filename, file_path, bu, created_by=operator)
    # 入队到独立后台 worker 串行执行，立即返回；不占 web 请求线程池（避免拖垮整站）
    eval_worker.submit(task["task_id"], resume=False, operator=operator)
    return task


@router.post("/upload")
async def upload(
    user: EvalWrite,
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
    user: EvalWrite,
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
    user: EvalRead,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    bu: str = Query("", description="按业务单元过滤；空则返回全部"),
    keyword: str = Query("", description="按文件名模糊匹配；空则不过滤"),
    mode: str = Query("", description="按评测模式过滤：calibration/production；空则不过滤"),
):
    tasks, total = eval_engine.list_tasks_paged(page, page_size, bu=bu, keyword=keyword, mode=mode)
    return success(page_data(tasks, page, page_size, total))


@router.get("/tasks/{task_id}")
async def task_status(task_id: str, user: EvalRead):
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    task["can_resume"] = eval_engine.can_resume(task_id)
    return success(task)


@router.get("/tasks/{task_id}/result")
async def task_result(task_id: str, user: EvalRead):
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
    user: EvalRead,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    flag: str = Query("all"),
    q: str = Query("", description="按客户问题关键字过滤"),
    intent: str = Query("", description="按业务分类过滤"),
    dispatched_bu: str = Query("", description="按分发BU关键字过滤"),
    j_dispatch: str = Query("", description="按分发判定过滤：是/否"),
    j_resolved: str = Query("", description="按是否解决过滤：是/否"),
):
    """分页查逐条评测明细（百万级下替代 /result 附带全量 rows）。

    flag=all（默认）按 row_index 分页，支持 q/intent/分发BU/分发判定/是否解决 多字段过滤；
    flag=review 只取需复核子集（有限上限）。「不一致」子集前端直接用 result.disagreements。
    """
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if flag == "review":
        rows = eval_engine.list_review_rows(task_id)
        return success(page_data(rows, 1, len(rows), len(rows)))
    filters = {"q": q, "intent": intent, "dispatched_bu": dispatched_bu,
               "j_dispatch": j_dispatch, "j_resolved": j_resolved}
    rows = eval_engine.list_rows(task_id, page, page_size, filters)
    total = eval_engine.count_rows(task_id, filters)
    return success(page_data(rows, page, page_size, total))


class ReviewBody(BaseModel):
    reviewed_dispatch: str = ""   # 是 / 否 / ''(不改)
    reviewed_resolved: str = ""   # 是 / 否 / ''(不改)
    reviewed_intent: str = ""     # 改后的业务分类('' 不改)
    comment: str = ""


@router.put("/tasks/{task_id}/rows/{row_index}/review")
async def submit_review(task_id: str, row_index: int, body: ReviewBody, user: EvalWrite):
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
async def delete_review(task_id: str, row_index: int, user: EvalWrite):
    """撤销某条明细的人工复核（该行恢复用 AI 判定，指标随之还原）。"""
    eval_engine.delete_review(task_id, row_index)
    return success({"deleted": True})


class DryrunBody(BaseModel):
    business_knowledge: str | None = None   # 详情页编辑框的临时业务知识；None=用库里已保存的


@router.post("/tasks/{task_id}/rows/{row_index}/dryrun")
async def dryrun_row(task_id: str, row_index: int, user: EvalWrite,
                     body: DryrunBody | None = None):
    """用当前提示词对该条重新试跑 Judge，返回新旧对比，不落库。
    body.business_knowledge 非空时用这段临时业务知识试跑（详情页改后未保存即可验证）。"""
    if not eval_engine.get_task(task_id):
        raise NotFoundError("任务不存在")
    biz = body.business_knowledge if body else None
    result = await eval_engine.dryrun_row(task_id, row_index, business_knowledge=biz)
    if result is None:
        raise NotFoundError("明细行不存在")
    return success(result)


class RerunRowsBody(BaseModel):
    row_indices: list[int]


def _rerun_result_or_raise(r: dict) -> dict:
    if r.get("error"):
        raise ParamError(r["error"])
    if r.get("over_limit"):
        raise ParamError(
            f"待重跑 {r['count']} 条，超过单次上限 {r['limit']} 条；请缩小范围或用「重新评测」全量重跑。")
    if not r.get("accepted"):
        raise ParamError(r.get("reason") or "没有可重跑的行")
    return r


@router.post("/tasks/{task_id}/rerun-subset")
async def rerun_subset(task_id: str, user: EvalWrite, flag: str = Query("review")):
    """按筛选(flag=review 待复核)异步重跑该子集。已排除人工复核过的行。
    立即返回，前端轮询任务状态看进度。"""
    if not eval_engine.get_task(task_id):
        raise NotFoundError("任务不存在")
    return success(_rerun_result_or_raise(eval_engine.rerun_subset(task_id, flag=flag, operator=user.username)))


@router.post("/tasks/{task_id}/rerun-rows")
async def rerun_rows(task_id: str, body: RerunRowsBody, user: EvalWrite):
    """异步重跑用户勾选的明细行（任意视图勾选）。已排除人工复核过的行。
    立即返回，前端轮询任务状态看进度；完成后指标全量重算。"""
    if not eval_engine.get_task(task_id):
        raise NotFoundError("任务不存在")
    if not body.row_indices:
        raise ParamError("未选择任何行")
    return success(_rerun_result_or_raise(
        eval_engine.rerun_rows_async(task_id, body.row_indices, operator=user.username)))


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str, user: EvalWrite):
    """暂停任务（running/pending → paused），腾出算力给别的任务，可随时恢复。"""
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if not eval_engine.pause_task(task_id):
        raise ParamError("该任务当前状态无法暂停（仅运行中/待执行可暂停）")
    return success(eval_engine.get_task(task_id))


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str, user: EvalWrite):
    """断点续跑：对中断的任务（暂停/失败等），跳过已完成行继续。

    先把 paused/interrupted 显式置 pending（worker 只抢 pending），再唤起 worker。
    failed 类走 submit(resume=True) 的原有语义。
    """
    task = eval_engine.get_task(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if not eval_engine.can_resume(task_id):
        raise ParamError("该任务无需或无法续跑")
    eval_engine.resume_task(task_id)   # paused/interrupted → pending（幂等，非该态则无操作）
    eval_worker.submit(task_id, resume=True, operator=user.username)
    return success(eval_engine.get_task(task_id))


@router.post("/tasks/{task_id}/rerun")
async def rerun_task(task_id: str, user: EvalWrite):
    """重新评测：清空已落盘结果，用当前提示词从头重跑。"""
    if not eval_engine.rerun_task(task_id):
        raise NotFoundError("任务不存在")
    eval_worker.submit(task_id, resume=False, operator=user.username)
    return success(eval_engine.get_task(task_id))


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: EvalWrite):
    """删除评测任务（连逐条结果一起硬删）。"""
    if not eval_engine.delete_task(task_id):
        raise NotFoundError("任务不存在")
    return success({"deleted": True})


@router.get("/tasks/{task_id}/export")
async def export_disagreements(task_id: str, user: EvalRead):
    path = eval_engine.export_disagreements(task_id)
    if not path:
        raise NotFoundError("无可导出结果")
    return FileResponse(path, media_type=_XLSX_MIME, filename=path.name)


@router.get("/tasks/{task_id}/export/rows")
async def export_rows(task_id: str, user: EvalRead):
    """逐条评测明细全量导出（两种模式都可用）。"""
    path = eval_engine.export_rows(task_id)
    if not path:
        raise NotFoundError("无可导出结果")
    return FileResponse(path, media_type=_XLSX_MIME, filename=path.name)


@router.get("/tasks/{task_id}/export/report")
async def export_report(task_id: str, user: EvalRead):
    """完整评估报告导出（概览/分发漏斗/洞察/建议 多 sheet）。"""
    path = eval_engine.export_report(task_id)
    if not path:
        raise NotFoundError("无可导出结果")
    return FileResponse(path, media_type=_XLSX_MIME, filename=path.name)


@router.get("/meta/bus")
async def get_bus(user: EvalRead):
    """列出可选业务单元（BU），供前端上传时选择。"""
    return success({"bus": list_bus()})


@router.get("/meta/intents")
async def get_intents(user: EvalRead, bu: str = "securities"):
    """返回指定 BU 的意图体系全集。"""
    return success({"bu": get_bu(bu).code, "intents": get_bu(bu).intent_list()})


@router.get("/meta/config")
async def get_config(user: EvalRead):
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
async def list_prompts(user: EvalRead, bu: str = "securities"):
    """某 BU 的全部模板槽位（专属/继承通用）+ 跨 BU 共享槽位。"""
    return success(eval_engine.list_prompts(bu))


@router.get("/prompts/{bu}/{name}")
async def get_prompt(bu: str, name: str, user: EvalRead):
    """单条提示词：当前有效内容 + 文件出厂默认 + 是否自定义。"""
    p = eval_engine.get_prompt(bu, name)
    if not p:
        raise NotFoundError("提示词不存在")
    return success(p)


@router.put("/prompts/{bu}/{name}")
async def save_prompt(bu: str, name: str, body: PromptSaveBody, user: EvalWrite):
    """保存提示词，立即生效（下次评测读到新值，无需重启）。"""
    if not body.content.strip():
        raise ParamError("提示词内容不能为空")
    return success(eval_engine.save_prompt(bu, name, body.content, operator=user.username))


@router.post("/prompts/{bu}/{name}/reset")
async def reset_prompt(bu: str, name: str, user: EvalWrite):
    """重置为文件出厂默认（删除库中自定义）。"""
    eval_engine.reset_prompt(bu, name)
    return success(eval_engine.get_prompt(bu, name))


# ── 业务分类管理（按 BU，页面增删改，改后不重启即生效）────────────────────────

class CategoryBody(BaseModel):
    name: str
    definition: str = ""


@router.get("/insights/questions")
async def insights_questions(
    user: EvalRead,
    bu: str = "securities",
    intent: str = "",
    start: str = "",
    end: str = "",
):
    """问题洞察：高频问榜单（按原文聚合）+ 每日提问频率。intent/start/end 为可选筛选。"""
    return success(eval_engine.question_insights(bu, intent=intent, start=start, end=end))


@router.get("/insights/keywords")
async def insights_keywords(user: EvalRead, bu: str = "securities", intent: str = ""):
    """问题洞察：按业务分类提炼的高区分关键词（jieba + TF-IDF，纯展示）。"""
    return success(eval_engine.keyword_insights(bu, intent=intent))


@router.get("/categories")
async def list_categories(user: EvalRead, bu: str = "securities"):
    """列出某 BU 的全部业务分类。"""
    return success({"bu": bu, "categories": eval_engine.list_categories(bu)})


@router.post("/categories")
async def create_category(user: EvalWrite, body: CategoryBody, bu: str = "securities"):
    """新增一个业务分类。"""
    if not body.name.strip():
        raise ParamError("分类名不能为空")
    return success(eval_engine.create_category(bu, body.name.strip(), body.definition, operator=user.username))


@router.put("/categories/{cat_id}")
async def update_category(cat_id: int, body: CategoryBody, user: EvalWrite):
    """更新业务分类名/定义。"""
    if not body.name.strip():
        raise ParamError("分类名不能为空")
    rec = eval_engine.update_category(cat_id, body.name.strip(), body.definition, operator=user.username)
    if not rec:
        raise NotFoundError("分类不存在")
    return success(rec)


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: int, user: EvalWrite):
    """删除业务分类。"""
    if not eval_engine.delete_category(cat_id):
        raise NotFoundError("分类不存在")
    return success({"deleted": True})


# ── 活动标问管理（写死按钮触发的写死回复，评测时整条跳过，不计入指标）────────────

class ActivityBody(BaseModel):
    question: str
    activity_name: str = ""
    note: str = ""


@router.get("/activity-questions")
async def list_activity_questions(user: EvalRead, bu: str = "securities"):
    """列出某 BU 的全部活动标问。"""
    return success({"bu": bu, "questions": eval_engine.list_activity_questions(bu)})


@router.post("/activity-questions")
async def create_activity_question(user: EvalWrite, body: ActivityBody, bu: str = "securities"):
    """新增一条活动标问（与客户问题精确相等即命中、整条跳过评测）。

    activity_name 指定所属活动（多个 question 同名即同活动，报告按活动聚合）；
    空则默认用 question 本身。已存在（同 bu+question）则更新活动名/备注。
    """
    if not body.question.strip():
        raise ParamError("活动标问不能为空")
    return success(eval_engine.create_activity_question(
        bu, body.question.strip(), note=body.note, activity_name=body.activity_name,
        operator=user.username))


@router.delete("/activity-questions/{act_id}")
async def delete_activity_question(act_id: int, user: EvalWrite):
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
async def list_rules(user: EvalRead, bu: str = "securities"):
    """列出某 BU 的全部短路规则。"""
    return success({"bu": bu, "rules": eval_engine.list_rules(bu)})


@router.post("/rules")
async def upsert_rule(user: EvalWrite, body: RuleBody, bu: str = "securities"):
    """新增/更新一条短路规则（按 (bu, question) upsert）。"""
    if not body.question.strip():
        raise ParamError("触发问题不能为空")
    if not isinstance(body.judge_json, dict) or not body.judge_json:
        raise ParamError("judge_json 不能为空")
    return success(eval_engine.upsert_rule(
        bu, body.question.strip(), body.expected_answer, body.judge_json,
        note=body.note, operator=user.username))


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, user: EvalWrite):
    """删除一条短路规则。"""
    if not eval_engine.delete_rule(rule_id):
        raise NotFoundError("规则不存在")
    return success({"deleted": True})
