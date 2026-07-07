"""AI 评测子系统的数据库访问层（与主体 DBManager 解耦）。

eval 不再往主体 DBManager 塞 eval_* 方法，而是自管一套薄访问层：
  - 复用主体的 engine / 连接池（同一物理库，不另开连接池）
  - 用独立 EvalBase 建自己的表（init_eval_schema，在应用启动时调一次）
  - 对外暴露模块级函数，内部走 EvalRepository / EvalPromptRepository

调用方（eval_engine / _store / prompt_loader）从 `from datapulse.modules.eval import eval_db`
取这些函数，不再依赖 `get_db().eval_*()`。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from datapulse.modules.eval.entities import EvalBase

_factory: sessionmaker | None = None


def _get_factory() -> sessionmaker:
    """懒初始化 eval 的 session 工厂，复用主体 engine（同一连接池）。"""
    global _factory
    if _factory is None:
        from datapulse.repository.base import get_db
        engine = get_db().engine          # 复用主体 engine
        _factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _factory


@contextmanager
def eval_session() -> Session:
    s = _get_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_eval_schema() -> None:
    """建 eval 自己的表（CREATE TABLE IF NOT EXISTS）。应用启动时调一次。"""
    from datapulse.repository.base import get_db
    EvalBase.metadata.create_all(get_db().engine)
    _seed_categories_from_file()


def _seed_categories_from_file() -> None:
    """首次启动把各 BU 的文件出厂分类导入库（仅当该 BU 库中为空）。

    让业务分类管理页一打开就有可编辑数据；已有数据的 BU 不动（用户改过的为准）。
    """
    from datapulse.modules.eval.bu.base import load_categories_from_file
    from datapulse.modules.eval.bu.registry import bu_codes

    for code in bu_codes():
        if category_count(code) > 0:
            continue
        file_cats = load_categories_from_file(code)
        if not file_cats:
            continue
        category_bulk_seed(code, [{"name": k, "definition": v} for k, v in file_cats.items()],
                           created_by="system")


# ── 任务 / 逐条结果 ───────────────────────────────────────────────────────────

def _repo(s: Session):
    from datapulse.modules.eval.repository import EvalRepository
    return EvalRepository(s)


def create_task(task_id: str, filename: str, file_path: str, bu: str,
                created_by: str = "system") -> None:
    with eval_session() as s:
        _repo(s).create_task(task_id, filename, file_path, bu, created_by=created_by)


def update_task(task_id: str, updated_by: str = "system", **fields: Any) -> None:
    with eval_session() as s:
        _repo(s).update_task(task_id, updated_by=updated_by, **fields)


def get_task(task_id: str) -> dict | None:
    with eval_session() as s:
        return _repo(s).get_task(task_id)


def get_task_status(task_id: str) -> str | None:
    """只取 status 一列，供评测循环的中断检查点每批轻量回查。记录不存在返回 None。"""
    with eval_session() as s:
        return _repo(s).get_task_status(task_id)


def list_tasks_paged(page: int, page_size: int, bu: str = "",
                     keyword: str = "", mode: str = "") -> tuple[list[dict], int]:
    with eval_session() as s:
        return _repo(s).list_tasks_paged(page, page_size, bu=bu, keyword=keyword, mode=mode)


# ── 多 POD 抢占式调度 ─────────────────────────────────────────────────────────

# 全局评测串行锁的 advisory key(任取一个进程间约定的常量即可,够独特避免与他处冲突)
_EVAL_ADVISORY_KEY = 0x6576616C  # "eval" 的 ASCII


def claim_next_task(worker_id: str) -> dict | None:
    with eval_session() as s:
        return _repo(s).claim_next_task(worker_id)


def heartbeat(task_id: str, worker_id: str) -> bool:
    with eval_session() as s:
        return _repo(s).heartbeat(task_id, worker_id)


def reclaim_stale(stale_seconds: int) -> int:
    from datetime import timedelta
    with eval_session() as s:
        return _repo(s).reclaim_stale(_now_ts() - timedelta(seconds=stale_seconds))


def requeue_idle() -> int:
    with eval_session() as s:
        return _repo(s).requeue_idle()


def _now_ts():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Shanghai"))


@contextmanager
def advisory_lock():
    """尝试拿全局评测串行锁(会话级 advisory lock)。拿到 yield True 并在退出时释放;
    拿不到(已有 POD 在跑评测)yield False。

    用独立连接持有,整个任务期间不放;评测落盘走各自的 eval_session,互不影响。
    保证全集群「同时只跑一个评测任务」,避免多 POD 一起压垮内网 LLM 网关。
    """
    from sqlalchemy import text

    from datapulse.repository.base import get_db
    conn = get_db().engine.connect()
    try:
        got = conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _EVAL_ADVISORY_KEY}
        ).scalar()
        if not got:
            yield False
            return
        try:
            yield True
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _EVAL_ADVISORY_KEY})
            conn.commit()
    finally:
        conn.close()


def delete_task(task_id: str) -> bool:
    with eval_session() as s:
        return _repo(s).delete_task(task_id)


def clear_rows(task_id: str) -> None:
    with eval_session() as s:
        _repo(s).clear_rows(task_id)


# 单次 insert 的子批大小：row_json 含答案原文/多轮上下文，单条可能数 KB~数十 KB。
# 内网 PG 中间层对单次大数据传输有连接超时，过大的 insert 会被切断
# （server closed the connection unexpectedly）。切小子批，每批独立短事务。
_SAVE_SUB_BATCH = 50
_SAVE_RETRIES = 3


def save_rows(task_id: str, rows: list[dict], created_by: str = "system") -> None:
    """逐条结果落盘。切成小子批、每批独立事务并自动重试，抗内网连接被切断。"""
    import time as _time

    for start in range(0, len(rows), _SAVE_SUB_BATCH):
        sub = rows[start:start + _SAVE_SUB_BATCH]
        for attempt in range(_SAVE_RETRIES):
            try:
                with eval_session() as s:          # 每批独立连接（pre_ping 探活）+ 独立事务
                    _repo(s).save_rows(task_id, sub, created_by=created_by)
                break
            except Exception:
                if attempt < _SAVE_RETRIES - 1:
                    _time.sleep(0.5 * (2 ** attempt))   # 退避后重连重试（下次 with 取新连接）
                    continue
                raise   # 重试耗尽，向上抛（评测引擎会 resume，已落盘子批不重做）


def done_row_indices(task_id: str) -> set[int]:
    with eval_session() as s:
        return _repo(s).done_row_indices(task_id)


def load_rows_filtered(task_id: str, page: int, page_size: int, filters: dict) -> list[dict]:
    with eval_session() as s:
        return _repo(s).load_rows_filtered(task_id, page, page_size, filters)


def count_rows_filtered(task_id: str, filters: dict) -> int:
    with eval_session() as s:
        return _repo(s).count_rows_filtered(task_id, filters)


def load_review_rows(task_id: str, limit: int = 500) -> list[dict]:
    with eval_session() as s:
        return _repo(s).load_review_rows(task_id, limit=limit)


def load_rows_after(task_id: str, after_index: int, limit: int) -> list[tuple[int, dict]]:
    with eval_session() as s:
        return _repo(s).load_rows_after(task_id, after_index, limit)


def load_rows_by_indices(task_id: str, indices: list[int]) -> dict[int, dict]:
    with eval_session() as s:
        return _repo(s).load_rows_by_indices(task_id, indices)


def rerun_subset_indices(task_id: str, flag: str) -> list[int]:
    with eval_session() as s:
        return _repo(s).rerun_subset_indices(task_id, flag)


def iter_all_row_jsons(task_id: str, batch_size: int = 1000):
    """跨独立 session 分批读回全部 row_json(全量重算 summary 用)。"""
    with eval_session() as s:
        # 在同一 session 内迭代完(生成器 yield 期间 session 保持打开)
        yield from _repo(s).iter_all_row_jsons(task_id, batch_size=batch_size)


def save_result(task_id: str, result: dict, updated_by: str = "system") -> None:
    with eval_session() as s:
        _repo(s).save_result(task_id, result, updated_by=updated_by)


def load_result(task_id: str) -> dict | None:
    with eval_session() as s:
        return _repo(s).load_result(task_id)


# ── 提示词 ────────────────────────────────────────────────────────────────────

def _prompt_repo(s: Session):
    from datapulse.modules.eval.repository import EvalPromptRepository
    return EvalPromptRepository(s)


def prompt_get(bu: str, name: str) -> dict | None:
    with eval_session() as s:
        return _prompt_repo(s).get(bu, name)


def prompt_list() -> list[dict]:
    with eval_session() as s:
        return _prompt_repo(s).list_all()


def prompt_upsert(bu: str, name: str, content: str,
                  description: str | None = None, updated_by: str = "system") -> dict:
    with eval_session() as s:
        return _prompt_repo(s).upsert(bu, name, content, description=description, updated_by=updated_by)


def prompt_delete(bu: str, name: str) -> bool:
    with eval_session() as s:
        return _prompt_repo(s).delete(bu, name)


# ── 业务分类 ──────────────────────────────────────────────────────────────────

def _cat_repo(s: Session):
    from datapulse.modules.eval.repository import EvalCategoryRepository
    return EvalCategoryRepository(s)


def category_list(bu: str) -> list[dict]:
    with eval_session() as s:
        return _cat_repo(s).list_by_bu(bu)


def category_count(bu: str) -> int:
    with eval_session() as s:
        return _cat_repo(s).count_by_bu(bu)


def category_create(bu: str, name: str, definition: str,
                    sort_order: int = 0, created_by: str = "system") -> dict:
    with eval_session() as s:
        return _cat_repo(s).create(bu, name, definition, sort_order=sort_order, created_by=created_by)


def category_update(cat_id: int, name: str | None = None, definition: str | None = None,
                    sort_order: int | None = None, updated_by: str = "system") -> dict | None:
    with eval_session() as s:
        return _cat_repo(s).update(cat_id, name=name, definition=definition,
                                   sort_order=sort_order, updated_by=updated_by)


def category_delete(cat_id: int) -> bool:
    with eval_session() as s:
        return _cat_repo(s).delete(cat_id)


def category_bulk_seed(bu: str, items: list[dict], created_by: str = "system") -> None:
    with eval_session() as s:
        _cat_repo(s).bulk_seed(bu, items, created_by=created_by)


# ── 活动标问 ──────────────────────────────────────────────────────────────────

def _act_repo(s: Session):
    from datapulse.modules.eval.repository import EvalActivityRepository
    return EvalActivityRepository(s)


def activity_list(bu: str) -> list[dict]:
    with eval_session() as s:
        return _act_repo(s).list_by_bu(bu)


def activity_list_questions(bu: str) -> list[tuple[str, str]]:
    with eval_session() as s:
        return _act_repo(s).list_questions(bu)


def activity_create(bu: str, question: str, note: str = "", activity_name: str = "",
                    created_by: str = "system") -> dict:
    with eval_session() as s:
        return _act_repo(s).create(bu, question, note=note, activity_name=activity_name,
                                   created_by=created_by)


def activity_create_many(bu: str, items: list[dict], created_by: str = "system") -> list[dict]:
    with eval_session() as s:
        return _act_repo(s).create_many(bu, items, created_by=created_by)


def activity_update(act_id: int, question: str, activity_name: str = "", note: str = "",
                    updated_by: str = "system") -> dict | None:
    with eval_session() as s:
        return _act_repo(s).update(act_id, question, activity_name=activity_name,
                                   note=note, updated_by=updated_by)


def activity_delete(act_id: int) -> bool:
    with eval_session() as s:
        return _act_repo(s).delete(act_id)


# ── 人工复核 ──────────────────────────────────────────────────────────────────

def _review_repo(s: Session):
    from datapulse.modules.eval.repository import EvalReviewRepository
    return EvalReviewRepository(s)


def review_upsert(task_id: str, row_index: int, *, reviewed_dispatch: str = "",
                  reviewed_resolved: str = "", reviewed_intent: str = "",
                  comment: str = "", reviewer: str = "system") -> dict:
    with eval_session() as s:
        return _review_repo(s).upsert(
            task_id, row_index, reviewed_dispatch=reviewed_dispatch,
            reviewed_resolved=reviewed_resolved, reviewed_intent=reviewed_intent,
            comment=comment, reviewer=reviewer)


def review_get(task_id: str, row_index: int) -> dict | None:
    with eval_session() as s:
        return _review_repo(s).get(task_id, row_index)


def review_list(task_id: str) -> list[dict]:
    with eval_session() as s:
        return _review_repo(s).list_by_task(task_id)


def review_delete(task_id: str, row_index: int) -> bool:
    with eval_session() as s:
        return _review_repo(s).delete(task_id, row_index)


# ── 规则短路 ──────────────────────────────────────────────────────────────────

def _rule_repo(s: Session):
    from datapulse.modules.eval.repository import EvalRuleRepository
    return EvalRuleRepository(s)


def rule_list(bu: str) -> list[dict]:
    with eval_session() as s:
        return _rule_repo(s).list_by_bu(bu)


def rule_list_for_match(bu: str) -> list[dict]:
    with eval_session() as s:
        return _rule_repo(s).list_for_match(bu)


def rule_upsert(bu: str, question: str, expected_answer: str, judge_json: dict,
                note: str = "", updated_by: str = "system") -> dict:
    with eval_session() as s:
        return _rule_repo(s).upsert(bu, question, expected_answer, judge_json,
                                    note=note, updated_by=updated_by)


def rule_delete(rule_id: int) -> bool:
    with eval_session() as s:
        return _rule_repo(s).delete(rule_id)


# ── 问题洞察聚合 ───────────────────────────────────────────────────────────────

def agg_top_questions(bu: str, intent: str = "", start: str = "",
                      end: str = "", limit: int = 100) -> tuple[list[dict], int]:
    with eval_session() as s:
        return _repo(s).agg_top_questions(bu, intent=intent, start=start, end=end, limit=limit)


def agg_daily_counts(bu: str, intent: str = "", start: str = "", end: str = "") -> list[dict]:
    with eval_session() as s:
        return _repo(s).agg_daily_counts(bu, intent=intent, start=start, end=end)


def agg_keyword_source(bu: str, intent: str = "",
                       limit_rows: int = 20000) -> tuple[list[tuple[str, str]], bool]:
    with eval_session() as s:
        return _repo(s).agg_keyword_source(bu, intent=intent, limit_rows=limit_rows)
