"""
向量索引模块（FAISS）
- FAISS 可用时使用 IndexFlatIP（内积，对归一化向量等价 cosine）
- FAISS 不可用时退化为 numpy 暴力搜索
索引文件持久化到 nas/vector_index/ 目录（由 EmbeddingStore 管理）
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from datapulse.repository.embeddings import get_emb

try:
    import faiss

    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False


class VectorIndex:
    def __init__(self) -> None:
        self._ids: list[str] = []
        self._vecs: np.ndarray | None = None
        self._faiss_index: Any = None
        self._dim: int = 768

    def build(self, id_vec_pairs: list[tuple[str, np.ndarray]]) -> None:
        if not id_vec_pairs:
            return
        self._ids = [p[0] for p in id_vec_pairs]
        self._vecs = np.stack([p[1] for p in id_vec_pairs]).astype(np.float32)
        self._dim = self._vecs.shape[1]
        if _FAISS_AVAILABLE:
            self._faiss_index = faiss.IndexFlatIP(self._dim)
            self._faiss_index.add(self._vecs)

    def add(self, item_id: str, vec: np.ndarray) -> None:
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

    def search(self, query_vec: np.ndarray, topk: int = 5) -> list[tuple[str, float]]:
        if self._vecs is None or len(self._ids) == 0:
            return []
        q = query_vec.astype(np.float32).reshape(1, -1)
        k = min(topk, len(self._ids))
        if _FAISS_AVAILABLE and self._faiss_index is not None:
            sims, idxs = self._faiss_index.search(q, k)
            results = [(self._ids[i], float(s)) for s, i in zip(sims[0], idxs[0]) if i >= 0]
        else:
            sims = (self._vecs @ q.T)[:, 0]
            top_idx = np.argsort(-sims)[:k]
            results = [(self._ids[i], float(sims[i])) for i in top_idx]
        return sorted(results, key=lambda x: -x[1])

    def save(self) -> None:
        emb = get_emb()
        ids_path = emb.vector_ids_path()
        index_path = emb.vector_index_path()
        with open(ids_path, "w") as f:
            json.dump(self._ids, f)
        if _FAISS_AVAILABLE and self._faiss_index is not None:
            faiss.write_index(self._faiss_index, str(index_path))
        elif self._vecs is not None:
            np.save(str(index_path.with_suffix(".npy")), self._vecs)

    def load(self) -> bool:
        emb = get_emb()
        ids_path = emb.vector_ids_path()
        index_path = emb.vector_index_path()
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


_index: VectorIndex | None = None


def get_index() -> VectorIndex:
    global _index
    if _index is None:
        _index = VectorIndex()
        _index.load()
    return _index


def rebuild_index() -> int:
    global _index
    emb = get_emb()
    all_embs = emb.load_all()
    pairs = list(all_embs.items())
    _index = VectorIndex()
    if pairs:
        _index.build(pairs)
        _index.save()
    return len(pairs)
