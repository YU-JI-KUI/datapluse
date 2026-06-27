"""评测模块的持久化适配层。

ark-dialog-eval 的 evaluator 以 `store.xxx()` 模块函数方式读写逐条结果（断点续跑），
此处把这些调用桥接到 datapulse 的 DBManager 代理方法，核心层无需改动。
"""
from __future__ import annotations

from datapulse.repository.base import get_db


def done_row_indices(task_id: str) -> set[int]:
    return get_db().eval_done_row_indices(task_id)


def load_rows(task_id: str) -> list[dict]:
    return get_db().eval_load_rows(task_id)


def iter_rows(task_id: str, batch_size: int = 1000):
    """分批读回已落盘行(按 row_index 排序),避免全量驻留内存。"""
    page = 1
    while True:
        batch = get_db().eval_load_rows_paged(task_id, page, batch_size)
        if not batch:
            break
        yield batch
        if len(batch) < batch_size:
            break
        page += 1


def save_rows(task_id: str, rows: list[dict]) -> None:
    get_db().eval_save_rows(task_id, rows)
