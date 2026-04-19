"""
向量索引模块（FAISS IndexIDMap，per-dataset 隔离）

设计要点：
1. 使用 IndexIDMap 包装 IndexFlatIP，FAISS 原生存储 int64 data_id，
   search() 直接返回 data_id，无需维护额外的 _ids 列表，彻底消除 str/int 混乱。
2. 每个 dataset 有独立索引，通过 dict[int, VectorIndex] 缓存。
3. FAISS 不可用时退化为 numpy 暴力搜索（同样存整型 ID）。
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import structlog

from datapulse.repository.embeddings import get_emb

_log = structlog.get_logger(__name__)

try:
    import faiss

    # 注意：不在这里调用 faiss.omp_set_num_threads()。
    # 调用该函数会在 import 时立刻初始化 FAISS 的 OpenMP 运行时；
    # 之后 torch/sentence_transformers 再初始化自己的 OpenMP 就会触发
    # "OMP Error #15: already initialized" 并 Abort。
    # 线程数限制由 main.py 顶部的 OMP_NUM_THREADS 环境变量统一控制。
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False


class VectorIndex:
    """单个 dataset 的向量索引"""

    def __init__(self, dataset_id: int, dim: int = 768) -> None:
        self._dataset_id = dataset_id
        self._dim        = dim
        # FAISS 路径
        self._faiss_index: Any = None
        # numpy 兜底路径
        self._np_ids:  list[int]         = []
        self._np_vecs: np.ndarray | None = None

    # ── 构建 ───────────────────────────────────────────────────────────────────

    def build(self, id_vec_pairs: list[tuple[int, np.ndarray]]) -> None:
        """从 [(data_id, vector), ...] 构建索引"""
        if not id_vec_pairs:
            return
        ids  = [p[0] for p in id_vec_pairs]
        vecs = np.stack([p[1] for p in id_vec_pairs]).astype(np.float32)
        self._dim = vecs.shape[1]

        if _FAISS_AVAILABLE:
            ids_arr = np.array(ids, dtype=np.int64)
            base    = faiss.IndexFlatIP(self._dim)
            self._faiss_index = faiss.IndexIDMap(base)
            self._faiss_index.add_with_ids(vecs, ids_arr)
        else:
            self._np_ids  = ids
            self._np_vecs = vecs

    # ── 搜索 ───────────────────────────────────────────────────────────────────

    def search(self, query_vec: np.ndarray, topk: int = 5) -> list[tuple[int, float]]:
        """返回 [(data_id: int, similarity: float), ...] 按相似度降序"""
        if self.size == 0:
            return []
        q = query_vec.astype(np.float32).reshape(1, -1)
        k = min(topk, self.size)

        if _FAISS_AVAILABLE and self._faiss_index is not None:
            sims, ids = self._faiss_index.search(q, k)
            return [
                (int(i), float(s))
                for s, i in zip(sims[0], ids[0])
                if i >= 0  # FAISS 用 -1 表示空槽
            ]
        else:
            # numpy 兜底
            assert self._np_vecs is not None
            sims_np = (self._np_vecs @ q.T)[:, 0]
            top_idx = np.argsort(-sims_np)[:k]
            return [(self._np_ids[i], float(sims_np[i])) for i in top_idx]

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def save(self) -> None:
        """保存索引到磁盘（仅 FAISS 模式有持久化文件）"""
        emb = get_emb()
        path = emb.vector_index_path(self._dataset_id)
        if _FAISS_AVAILABLE and self._faiss_index is not None:
            faiss.write_index(self._faiss_index, str(path))
        elif self._np_vecs is not None:
            # numpy 兜底：把 vecs 和 ids 分别保存
            np.save(str(path.with_suffix(".vecs.npy")), self._np_vecs)
            np.save(str(path.with_suffix(".ids.npy")),  np.array(self._np_ids, dtype=np.int64))

    def load(self) -> bool:
        """从磁盘加载索引，返回是否成功"""
        emb  = get_emb()
        path = emb.vector_index_path(self._dataset_id)
        if _FAISS_AVAILABLE and path.exists():
            self._faiss_index = faiss.read_index(str(path))
            self._dim = self._faiss_index.d
            return True
        # numpy 兜底
        vecs_path = path.with_suffix(".vecs.npy")
        ids_path  = path.with_suffix(".ids.npy")
        if vecs_path.exists() and ids_path.exists():
            self._np_vecs = np.load(str(vecs_path))
            self._np_ids  = np.load(str(ids_path)).tolist()
            if self._np_vecs.ndim == 2:
                self._dim = self._np_vecs.shape[1]
            return True
        return False

    # ── 属性 ──────────────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        if _FAISS_AVAILABLE and self._faiss_index is not None:
            return self._faiss_index.ntotal
        return len(self._np_ids)


# ── 全局 per-dataset 缓存 ──────────────────────────────────────────────────────

_index_cache: dict[int, VectorIndex] = {}


def get_index(dataset_id: int) -> VectorIndex:
    """懒加载：命中缓存则直接返回，否则从磁盘加载"""
    if dataset_id not in _index_cache:
        idx    = VectorIndex(dataset_id)
        loaded = idx.load()
        _index_cache[dataset_id] = idx
        if loaded:
            _log.info("vector index loaded from disk", dataset_id=dataset_id, size=idx.size)
        else:
            _log.info("vector index not found on disk (empty)", dataset_id=dataset_id)
    return _index_cache[dataset_id]


def rebuild_index(dataset_id: int) -> int:
    """从磁盘向量文件重建指定 dataset 的 FAISS 索引，返回索引向量数"""
    emb        = get_emb()
    id_vec_map = emb.load_all(dataset_id)  # {item_id(int): ndarray}
    _log.info("rebuilding vector index", dataset_id=dataset_id, vectors=len(id_vec_map))

    t0  = time.time()
    idx = VectorIndex(dataset_id)
    if id_vec_map:
        pairs = list(id_vec_map.items())
        idx.build(pairs)
        idx.save()

    # 更新缓存（无论是否有向量都更新，清除旧缓存）
    _index_cache[dataset_id] = idx
    _log.info(
        "vector index rebuilt",
        dataset_id=dataset_id, size=idx.size,
        elapsed_s=round(time.time() - t0, 2),
        backend="faiss" if _FAISS_AVAILABLE else "numpy",
    )
    return idx.size


def invalidate_index(dataset_id: int) -> None:
    """使指定 dataset 的索引缓存失效（配置更新后调用）"""
    _index_cache.pop(dataset_id, None)
