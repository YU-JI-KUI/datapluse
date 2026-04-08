"""
PostgreSQL 数据库存储层

职责：
  - DataItem CRUD（按 dataset 隔离）
  - ExportTemplate CRUD（按 dataset 隔离）
  - PipelineStatus 读写（按 dataset 隔离）
  - Dataset CRUD
  - SystemConfig 读写（按 dataset 隔离，JSON 格式）
  - User / Role / UserRole CRUD（RBAC）

Embedding 向量文件仍保留本地（storage/embeddings.py），FAISS 不适合存数据库。
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from passlib.context import CryptContext
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from storage.models import (
    Base, DataItem, Dataset, ExportTemplate,
    PipelineStatus, Role, SystemConfig, User, UserRole,
)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _now() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


# ── 默认配置（新建 dataset 时的初始值）────────────────────────────────────────

DEFAULT_DATASET_CONFIG: dict[str, Any] = {
    "llm": {
        "use_mock": True,
        "api_url": "http://internal-llm-platform/api/v1/chat",
        "model_name": "internal-llm",
        "timeout": 30,
    },
    "embedding": {
        "use_mock": True,
        "model_path": "./models/bge-base-zh",
        "batch_size": 64,
    },
    "similarity": {
        "threshold_high": 0.9,
        "threshold_mid": 0.8,
        "topk": 5,
    },
    "pipeline": {
        "batch_size": 32,
    },
    "labels": ["寿险意图", "拒识", "健康险意图", "财险意图", "其他意图"],
}

# 默认导出字段列表
DEFAULT_COLUMNS = [
    {"source": "id",           "target": "id",           "include": True},
    {"source": "text",         "target": "text",          "include": True},
    {"source": "label",        "target": "label",         "include": True},
    {"source": "model_pred",   "target": "model_pred",    "include": True},
    {"source": "model_score",  "target": "model_score",   "include": True},
    {"source": "annotator",    "target": "annotator",     "include": True},
    {"source": "annotated_at", "target": "annotated_at",  "include": True},
    {"source": "source_file",  "target": "source_file",   "include": True},
    {"source": "created_at",   "target": "created_at",    "include": False},
]

# 所有可用源字段（前端模板编辑器使用）
AVAILABLE_FIELDS = [
    {"source": "id",            "label": "数据 ID"},
    {"source": "text",          "label": "原始文本"},
    {"source": "label",         "label": "人工标注标签"},
    {"source": "model_pred",    "label": "模型预测标签"},
    {"source": "model_score",   "label": "模型置信度"},
    {"source": "annotator",     "label": "标注员"},
    {"source": "annotated_at",  "label": "标注时间"},
    {"source": "source_file",   "label": "来源文件"},
    {"source": "created_at",    "label": "创建时间"},
    {"source": "updated_at",    "label": "更新时间"},
    {"source": "conflict_flag", "label": "冲突标记"},
    {"source": "conflict_type", "label": "冲突类型"},
    {"source": "status",        "label": "数据状态"},
]

# 预置角色定义（首次启动时写入 DB）
PRESET_ROLES = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "admin",
        "description": "超级管理员，拥有所有权限",
        "permissions": ["*"],
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "name": "annotator",
        "description": "标注员，可查看数据、提交标注、执行导出",
        "permissions": [
            "data:read", "annotation:read", "annotation:write",
            "pipeline:read", "export:read", "export:create", "config:read",
        ],
    },
    {
        "id": "00000000-0000-0000-0000-000000000003",
        "name": "viewer",
        "description": "只读访问，可查看数据和导出结果",
        "permissions": ["data:read", "annotation:read", "pipeline:read", "export:read", "config:read"],
    },
]

DEFAULT_DATASET_ID = "00000000-0000-0000-0000-000000000010"


# ── ORM → dict 转换 ───────────────────────────────────────────────────────────

def _item_to_dict(item: DataItem) -> dict[str, Any]:
    return {
        "id":             item.id,
        "dataset_id":     item.dataset_id,
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
        "dataset_id":  t.dataset_id,
        "name":        t.name,
        "description": t.description,
        "format":      t.format,
        "columns":     t.columns or DEFAULT_COLUMNS,
        "filters":     t.filters or {"status": "checked", "include_conflicts": False},
        "created_at":  t.created_at,
        "updated_at":  t.updated_at,
    }


def _dataset_to_dict(d: Dataset) -> dict[str, Any]:
    return {
        "id":          d.id,
        "name":        d.name,
        "description": d.description,
        "is_active":   d.is_active,
        "created_at":  d.created_at,
        "updated_at":  d.updated_at,
    }


def _user_to_dict(u: User, roles: list[str] | None = None) -> dict[str, Any]:
    return {
        "id":            u.id,
        "username":      u.username,
        "email":         u.email or "",
        "is_active":     u.is_active,
        "roles":         roles or [],
        "created_at":    u.created_at,
        "updated_at":    u.updated_at,
        "last_login_at": u.last_login_at,
    }


def _role_to_dict(r: Role) -> dict[str, Any]:
    return {
        "id":          r.id,
        "name":        r.name,
        "description": r.description,
        "permissions": r.permissions or [],
        "created_at":  r.created_at,
    }


# ── DBManager ─────────────────────────────────────────────────────────────────

class DBManager:
    """PostgreSQL 存储管理器（单例）"""

    def __init__(self, db_url: str) -> None:
        self._engine = create_engine(
            db_url,
            pool_pre_ping=True,
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

    # ── 启动初始化 ────────────────────────────────────────────────────────────

    def seed_defaults(self) -> None:
        """首次启动时写入预置角色和默认数据集（幂等）"""
        with self._session() as s:
            # 预置角色
            for r in PRESET_ROLES:
                if not s.get(Role, r["id"]):
                    s.add(Role(
                        id=r["id"], name=r["name"],
                        description=r["description"],
                        permissions=r["permissions"],
                        created_at=_now(),
                    ))
            # 默认数据集
            if not s.get(Dataset, DEFAULT_DATASET_ID):
                s.add(Dataset(
                    id=DEFAULT_DATASET_ID,
                    name="默认数据集",
                    description="系统初始化创建的默认数据集",
                    is_active=True,
                    created_at=_now(),
                    updated_at=_now(),
                ))
            # 默认数据集配置
            if not s.get(SystemConfig, DEFAULT_DATASET_ID):
                s.add(SystemConfig(
                    dataset_id=DEFAULT_DATASET_ID,
                    config_data=DEFAULT_DATASET_CONFIG,
                    updated_at=_now(),
                    updated_by="system",
                ))

    def seed_admin_from_yaml(self, username: str, password: str) -> bool:
        """仅当 DB 中没有任何用户时，从 YAML 配置创建初始管理员（迁移用）"""
        with self._session() as s:
            count = s.query(func.count(User.id)).scalar()
            if count > 0:
                return False
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                password_hash=_pwd_ctx.hash(password),
                is_active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            s.add(user)
            s.flush()
            admin_role = s.query(Role).filter(Role.name == "admin").first()
            if admin_role:
                s.add(UserRole(user_id=user.id, role_id=admin_role.id, created_at=_now()))
        return True

    # ── Dataset ───────────────────────────────────────────────────────────────

    def list_datasets(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        with self._session() as s:
            q = s.query(Dataset)
            if not include_inactive:
                q = q.filter(Dataset.is_active == True)
            rows = q.order_by(Dataset.created_at).all()
        return [_dataset_to_dict(r) for r in rows]

    def get_dataset(self, dataset_id: str) -> Optional[dict[str, Any]]:
        with self._session() as s:
            row = s.get(Dataset, dataset_id)
            return _dataset_to_dict(row) if row else None

    def create_dataset(self, name: str, description: str = "") -> dict[str, Any]:
        ts = _now()
        ds_id = str(uuid.uuid4())
        with self._session() as s:
            row = Dataset(id=ds_id, name=name, description=description,
                          is_active=True, created_at=ts, updated_at=ts)
            s.add(row)
            # 同时为新 dataset 创建默认配置
            s.add(SystemConfig(
                dataset_id=ds_id,
                config_data=DEFAULT_DATASET_CONFIG,
                updated_at=ts,
                updated_by="system",
            ))
        return _dataset_to_dict(row)

    def update_dataset(self, dataset_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        with self._session() as s:
            row = s.get(Dataset, dataset_id)
            if row is None:
                return None
            for field in ("name", "description", "is_active"):
                if field in data:
                    setattr(row, field, data[field])
            row.updated_at = _now()
        return _dataset_to_dict(row)

    def delete_dataset(self, dataset_id: str) -> bool:
        with self._session() as s:
            row = s.get(Dataset, dataset_id)
            if row is None:
                return False
            s.delete(row)
        return True

    # ── SystemConfig ──────────────────────────────────────────────────────────

    def get_dataset_config(self, dataset_id: str) -> dict[str, Any]:
        """读取 dataset 配置，不存在则返回默认配置"""
        with self._session() as s:
            row = s.get(SystemConfig, dataset_id)
            if row is None:
                return dict(DEFAULT_DATASET_CONFIG)
            # 合并：默认值 + DB 存储值（DB 优先，支持部分缺失字段）
            import copy
            merged = copy.deepcopy(DEFAULT_DATASET_CONFIG)
            _deep_merge(merged, row.config_data or {})
            return merged

    def set_dataset_config(self, dataset_id: str, config_data: dict[str, Any],
                           updated_by: str = "system") -> dict[str, Any]:
        with self._session() as s:
            row = s.get(SystemConfig, dataset_id)
            if row is None:
                row = SystemConfig(dataset_id=dataset_id)
                s.add(row)
            row.config_data = config_data
            row.updated_at = _now()
            row.updated_by = updated_by
        return config_data

    # ── User ──────────────────────────────────────────────────────────────────

    def list_users(self) -> list[dict[str, Any]]:
        with self._session() as s:
            users = s.query(User).order_by(User.created_at).all()
            result = []
            for u in users:
                roles = self._get_user_roles_in_session(s, u.id)
                result.append(_user_to_dict(u, roles))
        return result

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        with self._session() as s:
            u = s.get(User, user_id)
            if u is None:
                return None
            roles = self._get_user_roles_in_session(s, user_id)
            return _user_to_dict(u, roles)

    def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        with self._session() as s:
            u = s.query(User).filter(User.username == username).first()
            if u is None:
                return None
            roles = self._get_user_roles_in_session(s, u.id)
            d = _user_to_dict(u, roles)
            d["password_hash"] = u.password_hash  # 供认证使用
            return d

    def create_user(self, username: str, password: str,
                    email: str = "", role_names: list[str] | None = None) -> dict[str, Any]:
        ts = _now()
        with self._session() as s:
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                email=email,
                password_hash=_pwd_ctx.hash(password),
                is_active=True,
                created_at=ts,
                updated_at=ts,
            )
            s.add(user)
            s.flush()
            roles = []
            for rname in (role_names or ["annotator"]):
                role = s.query(Role).filter(Role.name == rname).first()
                if role:
                    s.add(UserRole(user_id=user.id, role_id=role.id, created_at=ts))
                    roles.append(rname)
        return _user_to_dict(user, roles)

    def update_user(self, user_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        with self._session() as s:
            u = s.get(User, user_id)
            if u is None:
                return None
            if "email" in data:
                u.email = data["email"]
            if "is_active" in data:
                u.is_active = data["is_active"]
            if "password" in data and data["password"]:
                u.password_hash = _pwd_ctx.hash(data["password"])
            if "role_names" in data:
                s.query(UserRole).filter(UserRole.user_id == user_id).delete()
                for rname in data["role_names"]:
                    role = s.query(Role).filter(Role.name == rname).first()
                    if role:
                        s.add(UserRole(user_id=user_id, role_id=role.id, created_at=_now()))
            u.updated_at = _now()
            roles = self._get_user_roles_in_session(s, user_id)
        return _user_to_dict(u, roles)

    def update_last_login(self, user_id: str) -> None:
        with self._session() as s:
            u = s.get(User, user_id)
            if u:
                u.last_login_at = _now()

    def delete_user(self, user_id: str) -> bool:
        with self._session() as s:
            u = s.get(User, user_id)
            if u is None:
                return False
            s.delete(u)
        return True

    def verify_password(self, plain: str, hashed: str) -> bool:
        return _pwd_ctx.verify(plain, hashed)

    def _get_user_roles_in_session(self, s: Session, user_id: str) -> list[str]:
        rows = (
            s.query(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .filter(UserRole.user_id == user_id)
            .all()
        )
        return [r[0] for r in rows]

    # ── Role ──────────────────────────────────────────────────────────────────

    def list_roles(self) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.query(Role).order_by(Role.name).all()
        return [_role_to_dict(r) for r in rows]

    # ── DataItem ──────────────────────────────────────────────────────────────

    def create(self, dataset_id: str, text: str, source_file: str = "") -> dict[str, Any]:
        ts = _now()
        item = DataItem(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            text=text,
            status="raw",
            source_file=source_file,
            created_at=ts,
            updated_at=ts,
        )
        with self._session() as s:
            s.add(item)
        return _item_to_dict(item)

    def get(self, item_id: str) -> Optional[dict[str, Any]]:
        with self._session() as s:
            item = s.get(DataItem, item_id)
            return _item_to_dict(item) if item else None

    def update(self, item: dict[str, Any]) -> dict[str, Any]:
        item["updated_at"] = _now()
        with self._session() as s:
            row = s.get(DataItem, item["id"])
            if row is None:
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

    def list_all(self, dataset_id: str, status: Optional[str] = None,
                 page: int = 1, page_size: int = 20) -> dict[str, Any]:
        with self._session() as s:
            q = s.query(DataItem).filter(DataItem.dataset_id == dataset_id)
            if status:
                q = q.filter(DataItem.status == status)
            total = q.count()
            rows = (
                q.order_by(DataItem.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
        return {"total": total, "page": page, "page_size": page_size,
                "items": [_item_to_dict(r) for r in rows]}

    def list_by_status(self, dataset_id: str, status: str) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = (s.query(DataItem)
                    .filter(DataItem.dataset_id == dataset_id, DataItem.status == status)
                    .all())
        return [_item_to_dict(r) for r in rows]

    def stats(self, dataset_id: str) -> dict[str, int]:
        with self._session() as s:
            rows = (
                s.query(DataItem.status, func.count(DataItem.id))
                .filter(DataItem.dataset_id == dataset_id)
                .group_by(DataItem.status)
                .all()
            )
        result = {s: 0 for s in
                  ["raw", "processed", "pre_annotated", "labeling", "labeled", "checked"]}
        result["total"] = 0
        for status, cnt in rows:
            if status in result:
                result[status] = cnt
            result["total"] += cnt
        return result

    # ── Pipeline Status ────────────────────────────────────────────────────────

    def get_pipeline_status(self, dataset_id: str) -> dict[str, Any]:
        with self._session() as s:
            row = s.get(PipelineStatus, dataset_id)
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

    def set_pipeline_status(self, dataset_id: str, data: dict[str, Any]) -> None:
        with self._session() as s:
            row = s.get(PipelineStatus, dataset_id)
            if row is None:
                row = PipelineStatus(dataset_id=dataset_id)
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

    def list_templates(self, dataset_id: str) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = (s.query(ExportTemplate)
                    .filter(ExportTemplate.dataset_id == dataset_id)
                    .order_by(ExportTemplate.created_at.desc()).all())
        return [_template_to_dict(r) for r in rows]

    def get_template(self, template_id: str) -> Optional[dict[str, Any]]:
        with self._session() as s:
            row = s.get(ExportTemplate, template_id)
            return _template_to_dict(row) if row else None

    def create_template(self, dataset_id: str, data: dict[str, Any]) -> dict[str, Any]:
        ts = _now()
        row = ExportTemplate(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
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


# ── 工具函数 ───────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> None:
    """递归合并 override 到 base（原地修改）"""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


# ── 单例 ──────────────────────────────────────────────────────────────────────

_db: DBManager | None = None


def init_db(db_url: str) -> None:
    global _db
    _db = DBManager(db_url)


def get_db() -> DBManager:
    if _db is None:
        raise RuntimeError("DBManager 未初始化，请检查 main.py 中的 init_db() 调用")
    return _db
