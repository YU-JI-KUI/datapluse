"""
SQLAlchemy ORM 模型
数据库：PostgreSQL
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


class DataItem(Base):
    """意图识别数据条目"""

    __tablename__ = "data_items"

    id            = Column(String(36), primary_key=True, default=_uuid)
    text          = Column(Text, nullable=False)
    status        = Column(String(20), nullable=False, default="raw", index=True)
    label         = Column(String(200))
    model_pred    = Column(String(200))
    model_score   = Column(Float)
    annotator     = Column(String(100))
    annotated_at  = Column(String(30))
    conflict_flag = Column(Boolean, default=False)
    conflict_type = Column(String(50))
    conflict_detail = Column(JSONB)
    source_file   = Column(String(500))
    created_at    = Column(String(30), index=True)
    updated_at    = Column(String(30))


class ExportTemplate(Base):
    """导出模板：字段映射 + 格式 + 过滤条件"""

    __tablename__ = "export_templates"

    id          = Column(String(36), primary_key=True, default=_uuid)
    name        = Column(String(100), nullable=False)
    description = Column(Text)
    # json | excel | csv
    format      = Column(String(20), nullable=False, default="json")
    # 字段映射列表：[{source, target, include}, ...]
    # source = 数据字段名，target = 输出字段名，include = bool
    columns     = Column(JSONB)
    # 过滤条件：{status: "checked", include_conflicts: false}
    filters     = Column(JSONB)
    created_at  = Column(String(30))
    updated_at  = Column(String(30))


class PipelineStatus(Base):
    """Pipeline 运行状态（单行表，id 固定为 1）"""

    __tablename__ = "pipeline_status"

    id           = Column(Integer, primary_key=True, default=1)
    status       = Column(String(20), default="idle")
    current_step = Column(String(50))
    progress     = Column(Integer, default=0)
    detail       = Column(JSONB)
    started_at   = Column(String(30))
    finished_at  = Column(String(30))
    error        = Column(Text)
    updated_at   = Column(String(30))
