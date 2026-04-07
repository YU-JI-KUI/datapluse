"""
向量索引模块（FAISS）
- FAISS 可用时使用 IndexFlatIP（内积，对归一化向量等价 cosine）
- FAISS 不可用时退化为 numpy 暴力搜索
索引文件持久化到 NAS 的 vector_index/ 目录
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from storage.nas import get_nas

# ── FAISS 可选导入 ─────────────────────────────────────────────────────────
try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False


class VectorIndex:
    """
    封装 FAISS / numpy 暴力搜索，对外接口一致
    ids: 与向量对应的 item_id 列表
    """

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._vecs: np.ndarray | None = None   # shape (N, dim)
        self._faiss_index: Any = None
        self._dim: int = 768

    # ── 构建索引 ──────────────────────────────────────────────────────────

    def build(self, id_vec_pairs: list[tuple[str, np.ndarray]]) -> None:
        """从 (id, vector) 列表构建索引"""
        if not id_vec_pairs:
            return
        self._ids = [p[0] for p in id_vec_pairs]
        self._vecs = np.stack([p[1] for p in id_vec_pairs]).astype(np.float32)
        self._dim = self._vecs.shape[1]

        if _FAISS_AVAILABLE:
            self._faiss_index = faiss.IndexFlatIP(self._dim)
            self._faiss_index.add(self._vecs)

    def add(self, item_id: str, vec: np.ndarray) -> None:
        """增量添加单个向量"""
        vec = vec.astype(np.float32).reshape(1, -1)
        self._ids.append(item_id)
        if self._vecs is None:
            self._dim = vec.shape[1]
            self._vecs = vec
        else:
            self._vecs = np.vstack([self._vecs, vec])

        if _FAISS_AVAILABLE:
            if self._faiss_index is None:
                self._faiss_index = faiss.IndexFlatIP(self._dim)
            self._faiss_index.add(vec)

    # ── 检索 ──────────────────────────────────────────────────────────────

    def search(
        self, query_vec: np.ndarray, topk: int = 5
    ) -> list[tuple[str, float]]:
        """返回 [(item_id, similarity), ...] 按相似度降序"""
        if self._vecs is None or len(self._ids) == 0:
            return []

        q = query_vec.astype(np.float32).reshape(1, -1)
        k = min(topk, len(self._ids))

        if _FAISS_AVAILABLE and self._faiss_index is not None:
            sims, idxs = self._faiss_index.search(q, k)
            results = [
                (self._ids[i], float(s))
                for s, i in zip(sims[0], idxs[0])
                if i >= 0
            ]
        else:
            # numpy 暴力搜索
            sims = self._vecs @ q.T  # (N, 1)
            sims = sims[:, 0]
            top_idx = np.argsort(-sims)[:k]
            results = [(self._ids[i], float(sims[i])) for i in top_idx]

        return sorted(results, key=lambda x: -x[1])

    # ── 持久化 ────────────────────────────────────────────────────────────

    def save(self) -> None:
        nas = get_nas()
        index_path = nas.vector_index_path()
        ids_path = nas.vector_ids_path()

        # 保存 ids
        with open(ids_path, "w") as f:
            json.dump(self._ids, f)

        if _FAISS_AVAILABLE and self._faiss_index is not None:
            faiss.write_index(self._faiss_index, str(index_path))
        elif self._vecs is not None:
            # 退化：把向量矩阵存 npy
            np.save(str(index_path.with_suffix(".npy")), self._vecs)

    def load(self) -> bool:
        """加载已保存的索引，返回是否成功"""
        nas = get_nas()
        ids_path = nas.vector_ids_path()
        index_path = nas.vector_index_path()

        if not ids_path.exists():
            return False

        with open(ids_path) as f:
            self._ids = json.load(f)

        if _FAISS_AVAILABLE and index_path.exists():
            self._faiss_index = faiss.read_index(str(index_path))
            self._dim = self._faiss_index.d
        else:
            npy_path = index_path.with_suffix(".npy")
            if npy_path.exists():
                self._vecs = np.load(str(npy_path))
                self._dim = self._vecs.shape[1]

        return True

    @property
    def size(self) -> int:
        return len(self._ids)


# ── 全局单例 ───────────────────────────────────────────────────────────────

_index: VectorIndex | None = None


def get_index() -> VectorIndex:
    global _index
    if _index is None:
        _index = VectorIndex()
        _index.load()  # 尝试从磁盘恢复
    return _index


def rebuild_index() -> int:
    """从 NAS embeddings 目录重建完整索引，返回向量数量"""
    global _index
    nas = get_nas()
    all_embs = nas.load_all_embeddings()
    pairs = list(all_embs.items())

    _index = VectorIndex()
    if pairs:
        _index.build(pairs)
        _index.save()
    return len(pairs)
