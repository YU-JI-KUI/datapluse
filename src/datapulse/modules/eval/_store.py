"""评测模块的持久化适配层。

ark-dialog-eval 的 evaluator 以 `store.xxx()` 模块函数方式读写逐条结果（断点续跑），
此处桥接到 eval 子系统自管的 eval_db（已与主体 DBManager 解耦），核心层无需改动。
"""
from __future__ import annotations

from datapulse.modules.eval import eval_db


def done_row_indices(task_id: str) -> set[int]:
    return eval_db.done_row_indices(task_id)


def iter_rows(task_id: str, batch_size: int = 1000):
    """分批读回已落盘行(按 row_index 升序),避免全量驻留内存。

    用 keyset(row_index > 上批最大值)翻页,每批走 (task_id, row_index) 唯一索引定位,
    整体 O(N);OFFSET 分页读到后段要先扫过前面再丢弃,续跑读回会越翻越慢。
    """
    after = -1   # row_index 从 0 起,-1 保证取到第一条
    while True:
        batch = eval_db.load_rows_after(task_id, after, batch_size)
        if not batch:
            break
        yield [row_json for _idx, row_json in batch]
        after = batch[-1][0]
        if len(batch) < batch_size:
            break


def save_rows(task_id: str, rows: list[dict], bu: str = "") -> None:
    eval_db.save_rows(task_id, rows, bu=bu)
