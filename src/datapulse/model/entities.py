"""SQLAlchemy ORM 模型（对应 database/init.sql v2.0）

表命名规范：t_ 前缀
主键策略：所有表使用 BIGSERIAL（BigInteger autoincrement）
时间字段：统一 TIMESTAMP(6)
用户字段：统一 username，不使用 user_id 做外键关联
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# ── 审计字段类型快捷引用 ──────────────────────────────────────────────────────
_TS = TIMESTAMP(precision=6)


class Dataset(Base):
    """t_dataset — 数据集（多 pipeline 隔离单元）"""

    __tablename__ = "t_dataset"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    name        = Column(String(100), nullable=False)
    description = Column(Text, nullable=False, default="")
    status      = Column(String(20), nullable=False, default="active")
    created_at  = Column(_TS, nullable=False)
    created_by  = Column(String(45), nullable=False, default="")
    updated_at  = Column(_TS, nullable=False)
    updated_by  = Column(String(45), nullable=False, default="")


class SystemConfig(Base):
    """t_system_config — 系统配置（每个 dataset 独立一行，JSONB 存储）"""

    __tablename__ = "t_system_config"

    dataset_id  = Column(BigInteger, primary_key=True)
    config_data = Column(JSONB, nullable=False, default=dict)
    updated_at  = Column(_TS, nullable=False)
    updated_by  = Column(String(45), nullable=False, default="")


class Role(Base):
    """t_role — RBAC 角色，permissions 为字符串数组，["*"] 表示全部"""

    __tablename__ = "t_role"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    name        = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=False, default="")
    permissions = Column(JSONB, nullable=False, default=list)
    created_at  = Column(_TS, nullable=False)
    created_by  = Column(String(45), nullable=False, default="")
    updated_at  = Column(_TS, nullable=False)
    updated_by  = Column(String(45), nullable=False, default="")


class User(Base):
    """t_user — 用户账号，密码以 bcrypt 哈希存储"""

    __tablename__ = "t_user"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    username      = Column(String(100), nullable=False, unique=True)
    email         = Column(String(200), nullable=False, default="")
    password_hash = Column(String(200), nullable=False)
    is_active     = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(_TS)
    created_at    = Column(_TS, nullable=False)
    created_by    = Column(String(45), nullable=False, default="")
    updated_at    = Column(_TS, nullable=False)
    updated_by    = Column(String(45), nullable=False, default="")


class UserRole(Base):
    """t_user_role — 用户-角色关联（username 逻辑外键，不使用 user_id）"""

    __tablename__ = "t_user_role"

    username   = Column(String(100), primary_key=True)
    role_name  = Column(String(50), primary_key=True)
    created_at = Column(_TS, nullable=False)
    created_by = Column(String(45), nullable=False, default="")


class DataItem(Base):
    """t_data_item — 数据条目（纯数据层，标注/冲突在独立表中）"""

    __tablename__ = "t_data_item"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id   = Column(BigInteger, nullable=False, index=True)
    content      = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    source       = Column(String(50), nullable=False, default="")
    source_ref   = Column(String(255), nullable=False, default="")
    # status 是 t_data_state.stage 的冗余字段，保持同步以支持快速过滤
    status       = Column(String(30), nullable=False, default="raw", index=True)
    created_at   = Column(_TS, nullable=False)
    created_by   = Column(String(45), nullable=False, default="")
    updated_at   = Column(_TS, nullable=False)
    updated_by   = Column(String(45), nullable=False, default="")


class DataState(Base):
    """t_data_state — 数据流转状态（控制流，与 DataItem 一对一）"""

    __tablename__ = "t_data_state"

    data_id    = Column(BigInteger, primary_key=True)
    stage      = Column(String(50), nullable=False, default="raw")
    updated_at = Column(_TS, nullable=False)
    updated_by = Column(String(45), nullable=False, default="")


class PreAnnotation(Base):
    """t_pre_annotation — LLM 预标注结果（支持多版本）"""

    __tablename__ = "t_pre_annotation"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    data_id    = Column(BigInteger, nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    label      = Column(String(200), nullable=False)
    score      = Column(Numeric(5, 4))
    cot        = Column(Text, nullable=True)   # Chain of Thought 推理过程
    version    = Column(Integer, nullable=False, default=1)
    created_at = Column(_TS, nullable=False)
    created_by = Column(String(45), nullable=False, default="")


class Annotation(Base):
    """t_annotation — 人工标注（多人 × 多版本）"""

    __tablename__ = "t_annotation"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    data_id    = Column(BigInteger, nullable=False, index=True)
    username   = Column(String(100), nullable=False)
    label      = Column(String(200), nullable=False)
    cot        = Column(Text, nullable=True)   # Chain of Thought 标注理由
    version    = Column(Integer, nullable=False, default=1)
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(_TS, nullable=False)
    created_by = Column(String(45), nullable=False, default="")


class DataComment(Base):
    """t_data_comment — 数据评论（标注讨论）"""

    __tablename__ = "t_data_comment"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    data_id    = Column(BigInteger, nullable=False, index=True)
    username   = Column(String(100), nullable=False)
    comment    = Column(Text, nullable=False)
    created_at = Column(_TS, nullable=False)
    created_by = Column(String(45), nullable=False, default="")


class Conflict(Base):
    """t_conflict — 冲突检测记录（标注冲突 + 语义冲突）"""

    __tablename__ = "t_conflict"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    data_id       = Column(BigInteger, nullable=False, index=True)
    conflict_type = Column(String(50), nullable=False)
    detail        = Column(JSONB, nullable=False, default=dict)
    status        = Column(String(20), nullable=False, default="open")
    created_at    = Column(_TS, nullable=False)
    created_by    = Column(String(45), nullable=False, default="")


class ExportTemplate(Base):
    """t_export_template — 导出模板（字段映射 + 格式 + 过滤条件）"""

    __tablename__ = "t_export_template"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id  = Column(BigInteger, nullable=False, index=True)
    name        = Column(String(100), nullable=False)
    description = Column(Text, nullable=False, default="")
    format      = Column(String(20), nullable=False, default="json")
    columns     = Column(JSONB)
    filters     = Column(JSONB)
    created_at  = Column(_TS, nullable=False)
    created_by  = Column(String(45), nullable=False, default="")
    updated_at  = Column(_TS, nullable=False)
    updated_by  = Column(String(45), nullable=False, default="")


class PipelineStatus(Base):
    """t_pipeline_status — Pipeline 运行状态（每个 dataset 独立一行）"""

    __tablename__ = "t_pipeline_status"

    dataset_id   = Column(BigInteger, primary_key=True)
    status       = Column(String(20), nullable=False, default="idle")
    current_step = Column(String(50), nullable=False, default="")
    progress     = Column(Integer, nullable=False, default=0)
    detail       = Column(JSONB)
    started_at   = Column(_TS)
    finished_at  = Column(_TS)
    error        = Column(Text)
    updated_at   = Column(_TS, nullable=False)
    updated_by   = Column(String(45), nullable=False, default="")


class UserDataset(Base):
    """t_user_dataset — 用户-数据集访问权限（多对多关联）

    admin 用户可访问所有数据集，无需入此表。
    annotator / viewer 用户只能访问分配给自己的数据集。
    """

    __tablename__ = "t_user_dataset"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    username   = Column(String(100), nullable=False)
    dataset_id = Column(BigInteger, nullable=False)
    created_at = Column(_TS, nullable=False)
    created_by = Column(String(45), nullable=False, default="")


class AnnotationResult(Base):
    """t_annotation_result — 标注结果汇总（每条数据一行，由标注写入自动触发聚合）

    label_source:
      "auto"   — 多数投票自动计算（标注员提交/撤销时触发）
      "manual" — 冲突裁决后手动设定（冲突解决时写入）
    """

    __tablename__ = "t_annotation_result"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    data_id         = Column(BigInteger, nullable=False, unique=True, index=True)
    dataset_id      = Column(BigInteger, nullable=False, index=True)
    final_label     = Column(String(200), nullable=True)       # 最终标注标签（可为 None）
    label_source    = Column(String(20),  nullable=False, default="auto")  # "auto" | "manual"
    annotator_count = Column(Integer,     nullable=False, default=0)       # 当前有效标注人数
    resolver        = Column(String(100), nullable=True)                   # 裁决人（仅 manual）
    cot             = Column(Text,        nullable=True)                   # 裁决 COT（manual 时填写）
    updated_at      = Column(_TS, nullable=False)
    updated_by      = Column(String(45), nullable=False, default="")
