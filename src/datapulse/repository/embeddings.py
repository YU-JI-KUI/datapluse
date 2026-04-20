"""
Embedding 向量文件存储（per-dataset 隔离）

目录结构（base_path 来自各 dataset 的配置中心 storage.base_path）：
  {base_path}/embeddings/{dataset_id}/{item_id}.npy   — 单条向量文件
  {base_path}/vector_index/{dataset_id}/faiss.index   — FAISS 索引（IDMap 格式，含 int64 IDs）

NAS 基础路径不再从环境变量读取，改为每个 dataset 独立配置（配置中心 → 存储路径）。
默认值：/ark-nav/datapulse
不同 dataset 的向量和索引严格分开，互不干扰。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

_DEFAULT_BASE_PATH = "/ark-nav/datapulse"


def _get_base_path(dataset_id: int) -> Path:
    """从数据集配置中读取 storage.base_path；配置不存在时用默认值。

    延迟导入 get_db 避免循环依赖（base.py ↔ embeddings.py）。
    """
    try:
        from datapulse.repository.base import get_db
        db  = get_db()
        cfg = db.get_dataset_config(dataset_id)
        raw = cfg.get("storage", {}).get("base_path", _DEFAULT_BASE_PATH)
        return Path(raw) if raw else Path(_DEFAULT_BASE_PATH)
    except Exception:
        # DB 未初始化或配置缺失，回退到默认值
        return Path(_DEFAULT_BASE_PATH)


class EmbeddingStore:
    """本地向量文件存储（单例），所有方法均以 dataset_id 隔离。

    NAS 基础路径由各 dataset 的配置中心决定（storage.base_path），支持热更新。

    性能优化：
      - _path_cache 缓存各 dataset 的基础路径，避免每次 save/load 都触发 DB 查询。
      - get_existing_ids() 一次性扫描目录，供 step_embed 批量跳过已向量化的 item。
    """

    def __init__(self) -> None:
        self._path_cache: dict[int, Path] = {}

    def _base(self, dataset_id: int) -> Path:
        """获取 dataset 的 NAS 基础路径，结果按 dataset_id 缓存，避免重复 DB 查询。"""
        if dataset_id not in self._path_cache:
            p = _get_base_path(dataset_id)
            p.mkdir(parents=True, exist_ok=True)
            self._path_cache[dataset_id] = p
        return self._path_cache[dataset_id]

    def invalidate_path_cache(self, dataset_id: int) -> None:
        """storage.base_path 配置变更后调用，清除缓存使下次重新读取 DB。"""
        self._path_cache.pop(dataset_id, None)

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
