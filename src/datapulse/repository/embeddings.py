"""
Embedding 存储层（per-dataset 隔离）

架构说明
---------
向量数据（BYTEA）存于 PostgreSQL t_embedding 表，通过 EmbeddingRepository 操作。
FAISS 索引文件（faiss.index）仍存于 NAS，仅在 rebuild_index 时写入/读取。

目录结构（FAISS 索引）：
  {storage_base_path}/vector_index/{dataset_id}/faiss.index

性能对比
---------
旧方案（NAS .npy）：60k × 50ms/write ≈ 50 min
新方案（PG UPSERT）：60k ÷ 64 ≈ 1000 次 INSERT，亚分钟完成
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from datapulse.config.settings import get_settings


def _get_base_path() -> Path:
    """从 settings.storage_base_path 读取 NAS 根目录（进程级单例，不查 DB）。"""
    return Path(get_settings().storage_base_path)


class EmbeddingStore:
    """向量存储门面（单例）。

    向量读写通过 DatabaseClient（PostgreSQL），NAS 仅用于存放 FAISS 索引文件。
    _base_path 首次调用时缓存，避免重复读取 settings。
    """

    def __init__(self) -> None:
        self._base_path: Path | None = None

    def _base(self) -> Path:
        if self._base_path is None:
            p = _get_base_path()
            p.mkdir(parents=True, exist_ok=True)
            self._base_path = p
        return self._base_path

    def _idx_dir(self, dataset_id: int) -> Path:
        d = self._base() / "vector_index" / str(dataset_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── FAISS 索引路径（NAS） ─────────────────────────────────────────────────

    def vector_index_path(self, dataset_id: int) -> Path:
        return self._idx_dir(dataset_id) / "faiss.index"

    # ── 向量读取（通过 DB） ───────────────────────────────────────────────────

    def get_existing_ids(self, dataset_id: int) -> set[int]:
        """返回已存在向量的 data_id 集合（用于 step_embed 跳过已处理项）。"""
        from datapulse.repository.base import get_db
        return get_db().get_existing_embedding_ids(dataset_id)

    def load_all(self, dataset_id: int) -> dict[int, np.ndarray]:
        """加载 dataset 下全部向量 {item_id: vector}（用于重建 FAISS 索引）。"""
        from datapulse.repository.base import get_db
        return get_db().load_all_embeddings(dataset_id)

    def load_batch(self, dataset_id: int, item_ids: list[int]) -> dict[int, np.ndarray]:
        """批量加载指定 item_ids 的向量（供冲突检测使用）。"""
        from datapulse.repository.base import get_db
        return get_db().load_embeddings_batch(dataset_id, item_ids)


_emb: EmbeddingStore | None = None


def get_emb() -> EmbeddingStore:
    global _emb
    if _emb is None:
        _emb = EmbeddingStore()
    return _emb
