"""评测模块的持久化适配层。

ark-dialog-eval 的 evaluator 以 `store.xxx()` 模块函数方式读写逐条结果（断点续跑），
此处桥接到 eval 子系统自管的 eval_db（已与主体 DBManager 解耦），核心层无需改动。
"""
from __future__ import annotations

from datapulse.modules.eval import eval_db


def done_row_indices(task_id: str) -> set[int]:
    return eval_db.done_row_indices(task_id)


def load_rows(task_id: str) -> list[dict]:
    return eval_db.load_rows(task_id)


def iter_rows(task_id: str, batch_size: int = 1000):
    """分批读回已落盘行(按 row_index 排序),避免全量驻留内存。"""
    page = 1
    while True:
        batch = eval_db.load_rows_paged(task_id, page, batch_size)
        if not batch:
            break
        yield batch
        if len(batch) < batch_size:
            break
        page += 1


def save_rows(task_id: str, rows: list[dict]) -> None:
    eval_db.save_rows(task_id, rows)
