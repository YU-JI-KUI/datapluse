"""
Embedding 向量文件存储（per-dataset 隔离）

目录结构（base_path 来自 settings.storage_base_path，所有 dataset 共用同一 NAS 根目录）：
  {storage_base_path}/embeddings/{dataset_id}/{item_id}.npy   — 单条向量文件
  {storage_base_path}/vector_index/{dataset_id}/faiss.index   — FAISS 索引（IDMap 格式，含 int64 IDs）

不同 dataset 的向量和索引通过子目录严格隔离，互不干扰。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from datapulse.config.settings import get_settings


def _get_base_path() -> Path:
    """从 settings.storage_base_path 读取 NAS 根目录（进程级单例，不查 DB）。"""
    return Path(get_settings().storage_base_path)


class EmbeddingStore:
    """本地向量文件存储（单例），所有方法均以 dataset_id 隔离。

    NAS 基础路径统一从 settings.storage_base_path 读取（env 配置，全局共享）。
    _base_path 在首次调用时解析并缓存，进程内不变。

    性能优化：
      - _base_path 仅解析一次，所有 save/load 操作直接使用缓存路径。
      - get_existing_ids() 一次性扫描目录，供 step_embed 批量跳过已向量化的 item。
    """

    def __init__(self) -> None:
        self._base_path: Path | None = None

    def _base(self, dataset_id: int | None = None) -> Path:  # noqa: ARG002
        """获取 NAS 基础路径，首次调用时解析并缓存。dataset_id 保留以备子类扩展。"""
        if self._base_path is None:
            p = _get_base_path()
            p.mkdir(parents=True, exist_ok=True)
            self._base_path = p
        return self._base_path

    def _emb_dir(self, dataset_id: int) -> Path:
        d = self._base(dataset_id) / "embeddings" / str(dataset_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _idx_dir(self, dataset_id: int) -> Path:
        d = self._base(dataset_id) / "vector_index" / str(dataset_id)
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

    def get_existing_ids(self, dataset_id: int) -> set[int]:
        """一次性扫描 embedding 目录，返回已向量化的 item_id 集合。

        供 step_embed 在循环外预筛选，避免逐条 load() 检查文件是否存在。
        """
        d = self._emb_dir(dataset_id)
        return {int(p.stem) for p in d.glob("*.npy") if p.stem.isdigit()}

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
