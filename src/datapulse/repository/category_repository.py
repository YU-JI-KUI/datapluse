"""业务分类 Repository

CRUD + 批量导入（Excel 上传入口）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from datapulse.model.entities import Category


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_dict(row: Category) -> dict[str, Any]:
    return {
        "id":          row.id,
        "dataset_id":  row.dataset_id,
        "name":        row.name,
        "description": row.description,
        "created_at":  row.created_at.isoformat() if row.created_at else None,
        "created_by":  row.created_by,
        "updated_at":  row.updated_at.isoformat() if row.updated_at else None,
        "updated_by":  row.updated_by,
    }


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def list(self, dataset_id: int, keyword: str | None = None,
             page: int = 1, page_size: int = 10) -> dict:
        q = self.session.query(Category).filter(Category.dataset_id == dataset_id)
        if keyword:
            q = q.filter(Category.name.ilike(f"%{keyword}%"))
        total = q.count()
        rows  = q.order_by(Category.id).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "list":  [_to_dict(r) for r in rows],
            "total": total,
        }

    def get(self, category_id: int) -> dict | None:
        row = self.session.get(Category, category_id)
        return _to_dict(row) if row else None

    # ── 写入 ──────────────────────────────────────────────────────────────────

    def create(self, dataset_id: int, name: str, description: str = "",
               created_by: str = "system") -> dict:
        ts  = _now()
        row = Category(
            dataset_id  = dataset_id,
            name        = name.strip(),
            description = description,
            created_at  = ts,
            created_by  = created_by,
            updated_at  = ts,
            updated_by  = created_by,
        )
        self.session.add(row)
        self.session.flush()
        return _to_dict(row)

    def update(self, category_id: int, name: str | None = None,
               description: str | None = None, updated_by: str = "system") -> dict | None:
        row = self.session.get(Category, category_id)
        if not row:
            return None
        if name is not None:
            row.name = name.strip()
        if description is not None:
            row.description = description
        row.updated_at = _now()
        row.updated_by = updated_by
        self.session.flush()
        return _to_dict(row)

    def delete(self, category_id: int) -> bool:
        row = self.session.get(Category, category_id)
        if not row:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    def bulk_delete(self, category_ids: list[int]) -> int:
        """批量删除，返回实际删除条数（1 次 DELETE IN）。"""
        if not category_ids:
            return 0
        deleted = (
            self.session.query(Category)
            .filter(Category.id.in_(category_ids))
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return deleted

    # ── 批量导入 ──────────────────────────────────────────────────────────────

    def bulk_create(self, dataset_id: int, records: list[dict],
                    created_by: str = "system") -> dict:
        """幂等批量创建；同名分类跳过（ON CONFLICT DO NOTHING 语义）。

        records: [{"name": str, "description": str}, ...]
        返回: {"created": int, "skipped": int}
        """
        # 一次 IN 查询取已有名称集合，避免 N+1
        names     = [r["name"].strip() for r in records if r.get("name", "").strip()]
        existing  = {
            row.name
            for row in self.session.query(Category.name)
            .filter(Category.dataset_id == dataset_id, Category.name.in_(names))
            .all()
        }
        ts       = _now()
        created  = 0
        skipped  = 0
        for r in records:
            name = r.get("name", "").strip()
            if not name:
                skipped += 1
                continue
            if name in existing:
                skipped += 1
                continue
            self.session.add(Category(
                dataset_id  = dataset_id,
                name        = name,
                description = r.get("description", ""),
                created_at  = ts,
                created_by  = created_by,
                updated_at  = ts,
                updated_by  = created_by,
            ))
            existing.add(name)   # 防止同批次重复
            created += 1
        self.session.flush()
        return {"created": created, "skipped": skipped}
