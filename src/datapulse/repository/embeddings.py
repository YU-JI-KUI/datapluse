"""
Embedding 向量文件存储（最小化 NAS 依赖）

FAISS 索引和 numpy 向量必须以文件形式存储，无法放入数据库。
本模块仅保留向量相关的文件操作，其余数据全部由 DB 管理。
目录：nas/embeddings/ 和 nas/vector_index/（可配置）
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from datapulse.config.settings import get_settings


class EmbeddingStore:
    """本地向量文件存储（单例）"""

    def _base(self) -> Path:
        p = get_settings().storage_path
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _emb_dir(self) -> Path:
        d = self._base() / "embeddings"
        d.mkdir(exist_ok=True)
        return d

    def _idx_dir(self) -> Path:
        d = self._base() / "vector_index"
        d.mkdir(exist_ok=True)
        return d

    def save(self, item_id: str, vector: np.ndarray) -> None:
        np.save(str(self._emb_dir() / f"{item_id}.npy"), vector)

    def load(self, item_id: str) -> np.ndarray | None:
        p = self._emb_dir() / f"{item_id}.npy"
        return np.load(str(p)) if p.exists() else None

    def load_all(self) -> dict[str, np.ndarray]:
        return {p.stem: np.load(str(p)) for p in self._emb_dir().glob("*.npy")}

    def delete(self, item_id: str) -> None:
        p = self._emb_dir() / f"{item_id}.npy"
        if p.exists():
            p.unlink()

    def vector_index_path(self) -> Path:
        return self._idx_dir() / "faiss.index"

    def vector_ids_path(self) -> Path:
        return self._idx_dir() / "ids.json"


_emb: EmbeddingStore | None = None


def get_emb() -> EmbeddingStore:
    global _emb
    if _emb is None:
        _emb = EmbeddingStore()
    return _emb
