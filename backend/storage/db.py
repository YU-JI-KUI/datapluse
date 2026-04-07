"""
PostgreSQL 数据库存储层（替代 NAS 文件系统）

接口与原 NASManager 保持一致，调用方无需感知存储介质变化。
Embedding 向量文件仍保留在本地（storage/embeddings.py），
FAISS 索引需要 numpy 文件，不适合存数据库。
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from storage.models import Base, DataItem, ExportTemplate, PipelineStatus

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _to_dict(item: DataItem) -> dict[str, Any]:
    """ORM 对象 → 普通 dict（与原 NAS JSON 格式一致）"""
    return {
        "id":             item.id,
        "text":           item.text,
        "status":         item.status,
        "label":          item.label,
        "model_pred":     item.model_pred,
        "model_score":    item.model_score,
        "annotator":      item.annotator,
        "annotated_at":   item.annotated_at,
        "conflict_flag":  item.conflict_flag or False,
        "conflict_type":  item.conflict_type,
        "conflict_detail": item.conflict_detail,
        "source_file":    item.source_file,
        "created_at":     item.created_at,
        "updated_at":     item.updated_at,
    }


def _template_to_dict(t: ExportTemplate) -> dict[str, Any]:
    return {
        "id":          t.id,
        "name":        t.name,
        "description": t.description,
        "format":      t.format,
        "columns":     t.columns or DEFAULT_COLUMNS,
        "filters":     t.filters or {"status": "checked", "include_conflicts": False},
        "created_at":  t.created_at,
        "updated_at":  t.updated_at,
    }


# 默认导出字段（无模板时使用）
DEFAULT_COLUMNS = [
    {"source": "id",          "target": "id",           "include": True},
    {"source": "text",        "target": "text",          "include": True},
    {"source": "label",       "target": "label",         "include": True},
    {"source": "model_pred",  "target": "model_pred",    "include": True},
    {"source": "model_score", "target": "model_score",   "include": True},
    {"source": "annotator",   "target": "annotator",     "include": True},
    {"source": "annotated_at","target": "annotated_at",  "include": True},
    {"source": "source_file", "target": "source_file",   "include": True},
    {"source": "created_at",  "target": "created_at",    "include": False},
]

# 所有可用的源字段（用于前端渲染变量选择器）
AVAILABLE_FIELDS = [
    {"source": "id",             "label": "数据 ID"},
    {"source": "text",           "label": "原始文本"},
    {"source": "label",          "label": "人工标注标签"},
    {"source": "model_pred",     "label": "模型预测标签"},
    {"source": "model_score",    "label": "模型置信度"},
    {"source": "annotator",      "label": "标注员"},
    {"source": "annotated_at",   "label": "标注时间"},
    {"source": "source_file",    "label": "来源文件"},
    {"source": "created_at",     "label": "创建时间"},
    {"source": "updated_at",     "label": "更新时间"},
    {"source": "conflict_flag",  "label": "冲突标记"},
    {"source": "conflict_type",  "label": "冲突类型"},
    {"source": "status",         "label": "数据状态"},
]


class DBManager:
    """PostgreSQL 存储管理器（单例）"""

    def __init__(self, db_url: str) -> None:
        self._engine = create_engine(
            db_url,
            pool_pre_ping=True,   # 连接前检测是否存活
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

    @contextmanager
    def _session(self) -> Session:
        session = self._Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(self, text: str, source_file: str = "") -> dict[str, Any]:
        ts = _now()
        item = DataItem(
            id=str(uuid.uuid4()),
            text=text,
            status="raw",
            source_file=source_file,
            created_at=ts,
            updated_at=ts,
        )
        with self._session() as s:
            s.add(item)
        return _to_dict(item)

    def get(self, item_id: str) -> Optional[dict[str, Any]]:
        with self._session() as s:
            item = s.get(DataItem, item_id)
            return _to_dict(item) if item else None

    def update(self, item: dict[str, Any]) -> dict[str, Any]:
        item["updated_at"] = _now()
        with self._session() as s:
            row = s.get(DataItem, item["id"])
            if row is None:
                # 不存在则插入（幂等）
                row = DataItem(**{k: item.get(k) for k in DataItem.__table__.columns.keys()})
                s.add(row)
            else:
                for k, v in item.items():
                    if hasattr(row, k):
                        setattr(row, k, v)
        return item

    def delete(self, item_id: str) -> bool:
        with self._session() as s:
            row = s.get(DataItem, item_id)
            if row is None:
                return False
            s.delete(row)
        return True

    def list_all(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        with self._session() as s:
            q = s.query(DataItem)
            if status:
                q = q.filter(DataItem.status == status)
            total = q.count()
            rows = (
                q.order_by(DataItem.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_to_dict(r) for r in rows],
        }

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.query(DataItem).filter(DataItem.status == status).all()
        return [_to_dict(r) for r in rows]

    def stats(self) -> dict[str, int]:
        with self._session() as s:
            rows = (
                s.query(DataItem.status, func.count(DataItem.id))
                .group_by(DataItem.status)
                .all()
            )
        result = {status: 0 for status in
                  ["raw", "processed", "pre_annotated", "labeling", "labeled", "checked"]}
        result["total"] = 0
        for status, cnt in rows:
            if status in result:
                result[status] = cnt
            result["total"] += cnt
        return result

    # ── Pipeline status ────────────────────────────────────────────────────────

    def get_pipeline_status(self) -> dict[str, Any]:
        with self._session() as s:
            row = s.get(PipelineStatus, 1)
            if row is None:
                return {"status": "idle", "current_step": None, "progress": 0, "detail": {}}
            return {
                "status":       row.status,
                "current_step": row.current_step,
                "progress":     row.progress,
                "detail":       row.detail or {},
                "started_at":   row.started_at,
                "finished_at":  row.finished_at,
                "error":        row.error,
                "updated_at":   row.updated_at,
            }

    def set_pipeline_status(self, data: dict[str, Any]) -> None:
        with self._session() as s:
            row = s.get(PipelineStatus, 1)
            if row is None:
                row = PipelineStatus(id=1)
                s.add(row)
            row.status       = data.get("status", "idle")
            row.current_step = data.get("current_step")
            row.progress     = data.get("progress", 0)
            row.detail       = data.get("detail")
            row.started_at   = data.get("started_at")
            row.finished_at  = data.get("finished_at")
            row.error        = data.get("error")
            row.updated_at   = data.get("updated_at", _now())

    # ── Export Template ────────────────────────────────────────────────────────

    def list_templates(self) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.query(ExportTemplate).order_by(ExportTemplate.created_at.desc()).all()
        return [_template_to_dict(r) for r in rows]

    def get_template(self, template_id: str) -> Optional[dict[str, Any]]:
        with self._session() as s:
            row = s.get(ExportTemplate, template_id)
            return _template_to_dict(row) if row else None

    def create_template(self, data: dict[str, Any]) -> dict[str, Any]:
        ts = _now()
        row = ExportTemplate(
            id=str(uuid.uuid4()),
            name=data["name"],
            description=data.get("description", ""),
            format=data.get("format", "json"),
            columns=data.get("columns", DEFAULT_COLUMNS),
            filters=data.get("filters", {"status": "checked", "include_conflicts": False}),
            created_at=ts,
            updated_at=ts,
        )
        with self._session() as s:
            s.add(row)
        return _template_to_dict(row)

    def update_template(self, template_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        with self._session() as s:
            row = s.get(ExportTemplate, template_id)
            if row is None:
                return None
            for field in ("name", "description", "format", "columns", "filters"):
                if field in data:
                    setattr(row, field, data[field])
            row.updated_at = _now()
        return _template_to_dict(row)

    def delete_template(self, template_id: str) -> bool:
        with self._session() as s:
            row = s.get(ExportTemplate, template_id)
            if row is None:
                return False
            s.delete(row)
        return True


# ── 单例 ──────────────────────────────────────────────────────────────────────

_db: DBManager | None = None


def init_db(db_url: str) -> None:
    global _db
    _db = DBManager(db_url)


def get_db() -> DBManager:
    if _db is None:
        raise RuntimeError("DBManager 未初始化，请检查 main.py 中的 init_db() 调用")
    return _db
