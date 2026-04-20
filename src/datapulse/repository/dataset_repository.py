"""Dataset repository — t_dataset + t_system_config + t_user_dataset"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import Dataset, SystemConfig, UserDataset
from datapulse.repository.base import DEFAULT_DATASET_CONFIG

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _dataset_to_dict(d: Dataset) -> dict[str, Any]:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "status": d.status,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "created_by": d.created_by,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "updated_by": d.updated_by,
    }


class DatasetRepository:
    """Repository for Dataset entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_datasets(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        q = self.session.query(Dataset)
        if not include_inactive:
            q = q.filter(Dataset.status == "active")
        rows = q.order_by(Dataset.id).all()
        return [_dataset_to_dict(r) for r in rows]

    def get(self, dataset_id: int) -> dict[str, Any] | None:
        row = self.session.get(Dataset, dataset_id)
        return _dataset_to_dict(row) if row else None

    def create(self, name: str, description: str = "", created_by: str = "system") -> dict[str, Any]:
        ts = _now()
        row = Dataset(
            name=name,
            description=description,
            status="active",
            created_at=ts,
            created_by=created_by,
            updated_at=ts,
            updated_by=created_by,
        )
        self.session.add(row)
        self.session.flush()
        self.session.add(
            SystemConfig(
                dataset_id=row.id,
                config_data=DEFAULT_DATASET_CONFIG,
                updated_at=ts,
                updated_by="system",
            )
        )
        return _dataset_to_dict(row)

    def update(self, dataset_id: int, data: dict[str, Any], updated_by: str = "system") -> dict[str, Any] | None:
        row = self.session.get(Dataset, dataset_id)
        if row is None:
            return None
        for field in ("name", "description", "status"):
            if field in data:
                setattr(row, field, data[field])
        row.updated_at = _now()
        row.updated_by = updated_by
        return _dataset_to_dict(row)

    def delete(self, dataset_id: int) -> bool:
        row = self.session.get(Dataset, dataset_id)
        if row is None:
            return False
        self.session.delete(row)
        return True

    def delete_cascade(self, dataset_id: int) -> None:
        """级联删除数据集及其所有关联数据（后台异步执行）。

        删除顺序（无物理外键，按逻辑依赖从叶到根）：
          AnnotationResult → Annotation → PreAnnotation →
          Conflict → DataComment → DataState → DataItem →
          ExportTemplate → PipelineStatus → SystemConfig →
          UserDataset → Dataset
        """
        from datapulse.model.entities import (
            Annotation,
            AnnotationResult,
            Conflict,
            DataComment,
            DataItem,
            DataState,
            Embedding,
            ExportTemplate,
            PipelineStatus,
            PreAnnotation,
            UserDataset,
        )

        # 先查出所有 data_item id 便于关联表删除
        data_ids = [
            r[0]
            for r in self.session.query(DataItem.id)
            .filter(DataItem.dataset_id == dataset_id)
            .all()
        ]

        if data_ids:
            self.session.query(AnnotationResult).filter(
                AnnotationResult.data_id.in_(data_ids)
            ).delete(synchronize_session=False)
            self.session.query(Annotation).filter(
                Annotation.data_id.in_(data_ids)
            ).delete(synchronize_session=False)
            self.session.query(PreAnnotation).filter(
                PreAnnotation.data_id.in_(data_ids)
            ).delete(synchronize_session=False)
            self.session.query(Conflict).filter(
                Conflict.data_id.in_(data_ids)
            ).delete(synchronize_session=False)
            self.session.query(DataComment).filter(
                DataComment.data_id.in_(data_ids)
            ).delete(synchronize_session=False)
            self.session.query(DataState).filter(
                DataState.data_id.in_(data_ids)
            ).delete(synchronize_session=False)
            self.session.query(DataItem).filter(
                DataItem.dataset_id == dataset_id
            ).delete(synchronize_session=False)

        # t_embedding 按 dataset_id 直接删除，无需先查 data_ids
        self.session.query(Embedding).filter(
            Embedding.dataset_id == dataset_id
        ).delete(synchronize_session=False)

        self.session.query(ExportTemplate).filter(
            ExportTemplate.dataset_id == dataset_id
        ).delete(synchronize_session=False)
        self.session.query(PipelineStatus).filter(
            PipelineStatus.dataset_id == dataset_id
        ).delete(synchronize_session=False)
        self.session.query(SystemConfig).filter(
            SystemConfig.dataset_id == dataset_id
        ).delete(synchronize_session=False)
        self.session.query(UserDataset).filter(
            UserDataset.dataset_id == dataset_id
        ).delete(synchronize_session=False)

        row = self.session.get(Dataset, dataset_id)
        if row:
            self.session.delete(row)

    # ── 用户-数据集分配 ─────────────────────────────────────────────────────────

    def get_assigned_users(self, dataset_id: int) -> list[str]:
        """获取该数据集分配的所有用户名"""
        rows = (
            self.session.query(UserDataset)
            .filter(UserDataset.dataset_id == dataset_id)
            .all()
        )
        return [r.username for r in rows]

    def get_user_datasets(self, username: str) -> list[int]:
        """获取该用户被分配的所有数据集 id"""
        rows = (
            self.session.query(UserDataset)
            .filter(UserDataset.username == username)
            .all()
        )
        return [r.dataset_id for r in rows]

    def assign_users(self, dataset_id: int, usernames: list[str], by: str = "system") -> None:
        """将数据集分配给一批用户（覆盖式：先删除旧记录再写入新记录）"""
        self.session.query(UserDataset).filter(UserDataset.dataset_id == dataset_id).delete()
        ts = _now()
        for username in usernames:
            self.session.add(
                UserDataset(
                    username=username,
                    dataset_id=dataset_id,
                    created_at=ts,
                    created_by=by,
                )
            )

    def list_datasets_for_user(self, username: str, roles: list[str]) -> list[dict[str, Any]]:
        """普通用户只能看到分配给自己的活跃数据集"""
        if "admin" in roles:
            return self.list_datasets(include_inactive=False)
        assigned_ids = self.get_user_datasets(username)
        if not assigned_ids:
            return []
        rows = (
            self.session.query(Dataset)
            .filter(Dataset.status == "active", Dataset.id.in_(assigned_ids))
            .order_by(Dataset.id)
            .all()
        )
        return [_dataset_to_dict(r) for r in rows]
