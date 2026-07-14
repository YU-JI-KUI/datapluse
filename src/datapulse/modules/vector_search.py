"""
子进程 FAISS 批量检索（多线程精确检索）

背景
----
faiss 和 torch 各自捆绑一份 OpenMP 运行时，同进程内**多线程** faiss 检索
与 torch 会撞车（实测 SIGSEGV）。因此单线程之外无法在主进程提速。

方案
----
把 faiss 检索放到独立子进程执行：
  - 子进程用 spawn 启动（全新解释器，不继承主进程已初始化的 OpenMP 状态）
  - 子进程只 import faiss + 设线程数，**绝不 import torch**
  - 子进程自己从磁盘 read_index 加载索引（faiss 对象跨进程序列化不可靠，
    改传 dataset_id + 候选向量矩阵，索引文件本就在 NAS）
  - 一次性批量 search（M 条候选 × topk），比 Python 层逐条循环快得多

降级
----
子进程不可用（fork 受限 / faiss 缺失 / 加载失败）时，抛 SearchUnavailable，
调用方回退到原有的单线程 in-process 检索，保证功能不中断。
"""

from __future__ import annotations

import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import structlog

_log = structlog.get_logger(__name__)


class SearchUnavailable(Exception):
    """子进程检索不可用，调用方应降级到 in-process 单线程检索。"""


def _faiss_threads() -> int:
    """子进程检索线程数：留一个核给主进程，上限 8。"""
    cpu = os.cpu_count() or 2
    return max(1, min(cpu - 1, 8))


# ── 子进程 worker ─────────────────────────────────────────────────────────────
# 注意：本函数在 spawn 出来的干净子进程里执行，只 import faiss，绝不碰 torch。


def _worker_search(
    index_path: str,
    query_bytes: bytes,
    n_queries: int,
    dim: int,
    topk: int,
    threads: int,
) -> list[list[tuple[int, float]]]:
    """子进程内：加载索引 + 批量检索，返回每条查询的 [(data_id, sim), ...]。"""
    import faiss  # 仅子进程 import，主进程不受影响

    faiss.omp_set_num_threads(threads)
    index = faiss.read_index(index_path)

    queries = np.frombuffer(query_bytes, dtype=np.float32).reshape(n_queries, dim)
    k = min(topk, index.ntotal)
    if k <= 0:
        return [[] for _ in range(n_queries)]

    sims, ids = index.search(queries, k)   # 一次批量检索所有候选
    results: list[list[tuple[int, float]]] = []
    for row_sims, row_ids in zip(sims, ids):
        results.append([
            (int(i), float(s))
            for s, i in zip(row_sims, row_ids)
            if i >= 0   # faiss 用 -1 表示空槽
        ])
    return results


# ── 常驻子进程池（懒启动，进程级单例）─────────────────────────────────────────

_executor: ProcessPoolExecutor | None = None
_executor_broken = False


def _get_executor() -> ProcessPoolExecutor:
    """懒启动一个常驻的单 worker 子进程池（spawn context）。

    复用同一子进程，避免每次检索都付出进程启动开销。
    一旦启动失败标记为 broken，后续直接降级，不反复重试。
    """
    global _executor, _executor_broken
    if _executor_broken:
        raise SearchUnavailable("subprocess executor previously failed")
    if _executor is None:
        try:
            ctx = mp.get_context("spawn")
            _executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)
        except Exception as e:
            _executor_broken = True
            raise SearchUnavailable(f"cannot start subprocess executor: {e}") from e
    return _executor


def shutdown_executor() -> None:
    """关闭子进程池（FastAPI lifespan shutdown 调用）。"""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


def batch_search(
    index_path: str,
    query_vecs: np.ndarray,
    topk: int,
    timeout: float = 300.0,
) -> list[list[tuple[int, float]]]:
    """在子进程中对一批查询向量做精确检索。

    参数：
      index_path — faiss 索引文件路径（子进程自己 read_index）
      query_vecs — shape (M, dim) 的候选向量矩阵
      topk       — 每条查询返回的近邻数

    返回：长度 M 的列表，每项是 [(data_id, similarity), ...] 按相似度降序。

    子进程不可用时抛 SearchUnavailable，调用方降级。
    """
    if query_vecs.size == 0:
        return []
    if not os.path.exists(index_path):
        raise SearchUnavailable(f"index file not found: {index_path}")

    q = np.ascontiguousarray(query_vecs, dtype=np.float32)
    n, dim = q.shape
    executor = _get_executor()
    threads = _faiss_threads()
    try:
        fut = executor.submit(
            _worker_search, index_path, q.tobytes(), n, dim, topk, threads,
        )
        result = fut.result(timeout=timeout)
        _log.info(
            "subprocess batch search done",
            queries=n, topk=topk, threads=threads,
        )
        return result
    except SearchUnavailable:
        raise
    except Exception as e:
        # 子进程崩溃 / 超时：标记 broken 并降级
        global _executor, _executor_broken
        _log.warning("subprocess batch search failed, will fall back",
                     error=str(e), queries=n)
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None
        _executor_broken = True
        raise SearchUnavailable(f"subprocess search failed: {e}") from e
