"""SQLAlchemy ORM 模型

主键策略：
  - datasets       ：Integer SERIAL（自增）
  - roles          ：Integer SERIAL（自增）
  - users          ：Integer SERIAL（自增）
  - data_items     ：BigInteger SERIAL（自增，数据量可能较大）
  - export_templates：Integer SERIAL（自增）
  - system_config  ：dataset_id 为 FK，无独立主键
  - pipeline_status：dataset_id 为 FK，无独立主键
  - user_roles     ：(user_id, role_id) 联合主键
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Dataset(Base):
    """数据集：多 pipeline 隔离单元，不同 dataset 的数据、配置、模板完全独立"""

    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(30))
    updated_at = Column(String(30))


class SystemConfig(Base):
    """系统配置：每个 dataset 独立一行，所有参数存于 config_data JSONB。
    新增参数只需修改 JSON 结构，无需 ALTER TABLE。"""

    __tablename__ = "system_config"

    dataset_id = Column(Integer, primary_key=True)
    config_data = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(String(30))
    updated_by = Column(String(100))


class Role(Base):
    """RBAC 角色，permissions 为权限字符串数组，["*"] 表示全部权限"""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(Text)
    permissions = Column(JSONB, nullable=False, default=list)
    created_at = Column(String(30))


class User(Base):
    """用户账号，密码以 bcrypt 哈希存储"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(200))
    password_hash = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(30))
    updated_at = Column(String(30))
    last_login_at = Column(String(30))


class UserRole(Base):
    """用户-角色多对多关联（全局生效，不区分 dataset）"""

    __tablename__ = "user_roles"

    user_id = Column(Integer, primary_key=True)
    role_id = Column(Integer, primary_key=True)
    created_at = Column(String(30))


class DataItem(Base):
    """意图识别数据条目，随 pipeline 流转 status"""

    __tablename__ = "data_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, nullable=False, index=True)
    text = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="raw", index=True)
    label = Column(String(200))
    model_pred = Column(String(200))
    model_score = Column(Float)
    annotator = Column(String(100))
    annotated_at = Column(String(30))
    conflict_flag = Column(Boolean, default=False)
    conflict_type = Column(String(50))
    conflict_detail = Column(JSONB)
    source_file = Column(String(500))
    created_at = Column(String(30), index=True)
    updated_at = Column(String(30))


class ExportTemplate(Base):
    """导出模板：字段映射 + 格式 + 过滤条件，每个 dataset 独立管理"""

    __tablename__ = "export_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    format = Column(String(20), nullable=False, default="json")
    columns = Column(JSONB)
    filters = Column(JSONB)
    created_at = Column(String(30))
    updated_at = Column(String(30))


class PipelineStatus(Base):
    """Pipeline 运行状态，每个 dataset 独立一行"""

    __tablename__ = "pipeline_status"

    dataset_id = Column(Integer, primary_key=True)
    status = Column(String(20), default="idle")
    current_step = Column(String(50))
    progress = Column(Integer, default=0)
    detail = Column(JSONB)
    started_at = Column(String(30))
    finished_at = Column(String(30))
    error = Column(Text)
    updated_at = Column(String(30))
