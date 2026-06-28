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


def list_tasks() -> list[dict]:
    with eval_session() as s:
        return _repo(s).list_tasks()


def delete_task(task_id: str) -> bool:
    with eval_session() as s:
        return _repo(s).delete_task(task_id)


def clear_rows(task_id: str) -> None:
    with eval_session() as s:
        _repo(s).clear_rows(task_id)


def save_rows(task_id: str, rows: list[dict], created_by: str = "system") -> None:
    with eval_session() as s:
        _repo(s).save_rows(task_id, rows, created_by=created_by)


def done_row_indices(task_id: str) -> set[int]:
    with eval_session() as s:
        return _repo(s).done_row_indices(task_id)


def load_rows(task_id: str) -> list[dict]:
    with eval_session() as s:
        return _repo(s).load_rows(task_id)


def load_rows_paged(task_id: str, page: int, page_size: int) -> list[dict]:
    with eval_session() as s:
        return _repo(s).load_rows_paged(task_id, page, page_size)


def count_rows(task_id: str) -> int:
    with eval_session() as s:
        return _repo(s).count_rows(task_id)


def load_rows_filtered(task_id: str, page: int, page_size: int, q: str = "", intent: str = "") -> list[dict]:
    with eval_session() as s:
        return _repo(s).load_rows_filtered(task_id, page, page_size, q=q, intent=intent)


def count_rows_filtered(task_id: str, q: str = "", intent: str = "") -> int:
    with eval_session() as s:
        return _repo(s).count_rows_filtered(task_id, q=q, intent=intent)


def load_review_rows(task_id: str, limit: int = 500) -> list[dict]:
    with eval_session() as s:
        return _repo(s).load_review_rows(task_id, limit=limit)


def load_rows_after(task_id: str, after_index: int, limit: int) -> list[tuple[int, dict]]:
    with eval_session() as s:
        return _repo(s).load_rows_after(task_id, after_index, limit)


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
