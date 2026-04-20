"""Embedding repository — t_embedding

向量以 BYTEA 形式存储于 PostgreSQL，每条记录对应一个 (dataset_id, data_id) 唯一向量。
相比 NAS 上的 60k 个 .npy 文件，批量 UPSERT 大幅减少 I/O round-trip：
  - 旧方案：60k × 50ms NAS write ≈ 50 min
  - 新方案：60k ÷ 64 ≈ 1000 次 DB INSERT，亚分钟完成
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from datapulse.model.entities import Embedding

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _vec_to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def _bytes_to_vec(data: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32).reshape(dim)


class EmbeddingRepository:
    """Repository for Embedding entity（t_embedding）。

    主要操作：
      bulk_save        — 批量 UPSERT 向量（每批 batch_size 条，默认 64）
      get_existing_ids — 一次性查询已存在的 item_id 集合（供 step_embed 跳过已处理项）
      load_all         — 加载 dataset 全部向量（供重建 FAISS 索引）
      load_batch       — 按 item_id 列表加载向量（供冲突检测批量使用）
    """

    # 单次 UPSERT 的最大行数；过大会使 SQL 参数超限，过小会增加 round-trip
    BATCH_SIZE = 64

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── 写入 ──────────────────────────────────────────────────────────────────

    def bulk_save(
        self,
        dataset_id: int,
        id_vec_pairs: list[tuple[int, np.ndarray]],
        created_by: str = "pipeline",
    ) -> int:
        """批量 UPSERT 向量到 t_embedding。

        使用原生 SQL INSERT ... ON CONFLICT DO UPDATE 以获得最佳性能。
        返回写入总行数（包含 INSERT 和 UPDATE）。
        """
        if not id_vec_pairs:
            return 0

        upsert_sql = text("""
            INSERT INTO t_embedding (dataset_id, data_id, vector, dim, created_at)
            VALUES (:dataset_id, :data_id, :vector, :dim, :created_at)
            ON CONFLICT (dataset_id, data_id)
            DO UPDATE SET
                vector     = EXCLUDED.vector,
                dim        = EXCLUDED.dim,
                created_at = EXCLUDED.created_at
        """)

        ts    = _now()
        total = 0
        for i in range(0, len(id_vec_pairs), self.BATCH_SIZE):
            batch = id_vec_pairs[i : i + self.BATCH_SIZE]
            params = [
                {
                    "dataset_id": dataset_id,
                    "data_id":    item_id,
                    "vector":     _vec_to_bytes(vec),
                    "dim":        int(vec.shape[0]),
                    "created_at": ts,
                }
                for item_id, vec in batch
            ]
            self.session.execute(upsert_sql, params)
            total += len(batch)

        return total

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get_existing_ids(self, dataset_id: int) -> set[int]:
        """返回已存在向量的 data_id 集合（用于跳过已向量化的条目）。"""
        rows = (
            self.session.query(Embedding.data_id)
            .filter(Embedding.dataset_id == dataset_id)
            .all()
        )
        return {int(r.data_id) for r in rows}

    def load_all(self, dataset_id: int) -> dict[int, np.ndarray]:
        """加载 dataset 下全部向量，返回 {item_id: vector}。

        主要用于重建 FAISS 索引（rebuild_index）。
        """
        rows = (
            self.session.query(Embedding)
            .filter(Embedding.dataset_id == dataset_id)
            .all()
        )
        return {
            int(r.data_id): _bytes_to_vec(r.vector, r.dim)
            for r in rows
        }

    def load_batch(
        self,
        dataset_id: int,
        item_ids: list[int],
    ) -> dict[int, np.ndarray]:
        """按 item_id 列表批量加载向量，返回 {item_id: vector}。

        供冲突检测一次性取出所有候选向量，消除 N 次逐条 DB 查询。
        """
        if not item_ids:
            return {}
        rows = (
            self.session.query(Embedding)
            .filter(
                Embedding.dataset_id == dataset_id,
                Embedding.data_id.in_(item_ids),
            )
            .all()
        )
        return {
            int(r.data_id): _bytes_to_vec(r.vector, r.dim)
            for r in rows
        }
