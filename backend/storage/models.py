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


# ── 数据集 ────────────────────────────────────────────────────────────────────

class Dataset(Base):
    """数据集：多 pipeline 隔离单元，不同 dataset 的数据、配置、模板完全独立"""

    __tablename__ = "datasets"

    id          = Column(String(36), primary_key=True, default=_uuid)
    name        = Column(String(100), nullable=False)
    description = Column(Text)
    is_active   = Column(Boolean, nullable=False, default=True)
    created_at  = Column(String(30))
    updated_at  = Column(String(30))


# ── 系统配置 ───────────────────────────────────────────────────────────────────

class SystemConfig(Base):
    """系统配置：每个 dataset 独立一行，所有参数存于 config_data JSONB
    新增参数直接修改 JSON 结构即可，无需 ALTER TABLE"""

    __tablename__ = "system_config"

    dataset_id  = Column(String(36), primary_key=True)
    config_data = Column(JSONB, nullable=False, default=dict)
    updated_at  = Column(String(30))
    updated_by  = Column(String(100))


# ── RBAC ──────────────────────────────────────────────────────────────────────

class Role(Base):
    """角色：admin / annotator / viewer，permissions 为权限字符串数组"""

    __tablename__ = "roles"

    id          = Column(String(36), primary_key=True, default=_uuid)
    name        = Column(String(50), nullable=False, unique=True)
    description = Column(Text)
    permissions = Column(JSONB, nullable=False, default=list)  # ["data:read", ...]
    created_at  = Column(String(30))


class User(Base):
    """用户账号，密码以 bcrypt 哈希存储"""

    __tablename__ = "users"

    id            = Column(String(36), primary_key=True, default=_uuid)
    username      = Column(String(100), nullable=False, unique=True)
    email         = Column(String(200))
    password_hash = Column(String(200), nullable=False)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(String(30))
    updated_at    = Column(String(30))
    last_login_at = Column(String(30))


class UserRole(Base):
    """用户-角色关联（多对多），全局生效"""

    __tablename__ = "user_roles"

    user_id    = Column(String(36), primary_key=True)
    role_id    = Column(String(36), primary_key=True)
    created_at = Column(String(30))


# ── 业务数据 ───────────────────────────────────────────────────────────────────

class DataItem(Base):
    """意图识别数据条目，随 pipeline 流转 status"""

    __tablename__ = "data_items"

    id              = Column(String(36), primary_key=True, default=_uuid)
    dataset_id      = Column(String(36), nullable=False, index=True)
    text            = Column(Text, nullable=False)
    status          = Column(String(20), nullable=False, default="raw", index=True)
    label           = Column(String(200))
    model_pred      = Column(String(200))
    model_score     = Column(Float)
    annotator       = Column(String(100))
    annotated_at    = Column(String(30))
    conflict_flag   = Column(Boolean, default=False)
    conflict_type   = Column(String(50))
    conflict_detail = Column(JSONB)
    source_file     = Column(String(500))
    created_at      = Column(String(30), index=True)
    updated_at      = Column(String(30))


class ExportTemplate(Base):
    """导出模板：字段映射 + 格式 + 过滤条件，每个 dataset 独立管理"""

    __tablename__ = "export_templates"

    id          = Column(String(36), primary_key=True, default=_uuid)
    dataset_id  = Column(String(36), nullable=False, index=True)
    name        = Column(String(100), nullable=False)
    description = Column(Text)
    format      = Column(String(20), nullable=False, default="json")  # json|excel|csv
    columns     = Column(JSONB)   # [{source, target, include}, ...]
    filters     = Column(JSONB)   # {status, include_conflicts}
    created_at  = Column(String(30))
    updated_at  = Column(String(30))


class PipelineStatus(Base):
    """Pipeline 运行状态，每个 dataset 独立一行（dataset_id 为主键）"""

    __tablename__ = "pipeline_status"

    dataset_id   = Column(String(36), primary_key=True)
    status       = Column(String(20), default="idle")   # idle|running|completed|error
    current_step = Column(String(50))
    progress     = Column(Integer, default=0)
    detail       = Column(JSONB)
    started_at   = Column(String(30))
    finished_at  = Column(String(30))
    error        = Column(Text)
    updated_at   = Column(String(30))
