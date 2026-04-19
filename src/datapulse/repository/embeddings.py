"""
Embedding 向量文件存储（per-dataset 隔离）

目录结构：
  nas/embeddings/{dataset_id}/{item_id}.npy   — 单条向量文件
  nas/vector_index/{dataset_id}/faiss.index   — FAISS 索引（IDMap 格式，含 int64 IDs）

不同 dataset 的向量和索引严格分开，互不干扰。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from datapulse.config.settings import get_settings


class EmbeddingStore:
    """本地向量文件存储（单例），所有方法均以 dataset_id 隔离"""

    def _base(self) -> Path:
        p = get_settings().storage_path
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _emb_dir(self, dataset_id: int) -> Path:
        d = self._base() / "embeddings" / str(dataset_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _idx_dir(self, dataset_id: int) -> Path:
        d = self._base() / "vector_index" / str(dataset_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── 单条向量 ──────────────────────────────────────────────────────────────

    def save(self, dataset_id: int, item_id: int, vector: np.ndarray) -> None:
        np.save(str(self._emb_dir(dataset_id) / f"{item_id}.npy"), vector)

    def load(self, dataset_id: int, item_id: int) -> np.ndarray | None:
        p = self._emb_dir(dataset_id) / f"{item_id}.npy"
        return np.load(str(p)) if p.exists() else None

    def load_all(self, dataset_id: int) -> dict[int, np.ndarray]:
        """返回 {item_id(int): vector}，用于重建索引"""
        result: dict[int, np.ndarray] = {}
        for p in self._emb_dir(dataset_id).glob("*.npy"):
            try:
                result[int(p.stem)] = np.load(str(p))
            except (ValueError, Exception):
                pass
        return result

    def delete(self, dataset_id: int, item_id: int) -> None:
        p = self._emb_dir(dataset_id) / f"{item_id}.npy"
        if p.exists():
            p.unlink()

    # ── 索引文件路径 ──────────────────────────────────────────────────────────

    def vector_index_path(self, dataset_id: int) -> Path:
        return self._idx_dir(dataset_id) / "faiss.index"


_emb: EmbeddingStore | None = None


def get_emb() -> EmbeddingStore:
    global _emb
    if _emb is None:
        _emb = EmbeddingStore()
    return _emb
