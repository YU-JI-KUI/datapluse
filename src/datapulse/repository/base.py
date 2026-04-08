"""Database session management and initialization."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from datapulse.model.entities import Base, Dataset, Role, SystemConfig

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _hash_password(password: str) -> str:
    """bcrypt 哈希（直接调用 bcrypt 库，兼容 3.x / 4.x，无 passlib 依赖）"""
    import bcrypt as _bcrypt

    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配"""
    import bcrypt as _bcrypt

    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _now() -> str:
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


# 默认配置（新建 dataset 时的初始值）
DEFAULT_DATASET_CONFIG: dict = {
    "llm": {
        "use_mock": True,
        "api_url": "",
        "model_name": "",
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

DEFAULT_COLUMNS = [
    {"source": "id", "target": "id", "include": True},
    {"source": "text", "target": "text", "include": True},
    {"source": "label", "target": "label", "include": True},
    {"source": "model_pred", "target": "model_pred", "include": True},
    {"source": "model_score", "target": "model_score", "include": True},
    {"source": "annotator", "target": "annotator", "include": True},
    {"source": "annotated_at", "target": "annotated_at", "include": True},
    {"source": "source_file", "target": "source_file", "include": True},
    {"source": "created_at", "target": "created_at", "include": False},
]

AVAILABLE_FIELDS = [
    {"source": "id", "label": "数据 ID"},
    {"source": "text", "label": "原始文本"},
    {"source": "label", "label": "人工标注标签"},
    {"source": "model_pred", "label": "模型预测标签"},
    {"source": "model_score", "label": "模型置信度"},
    {"source": "annotator", "label": "标注员"},
    {"source": "annotated_at", "label": "标注时间"},
    {"source": "source_file", "label": "来源文件"},
    {"source": "created_at", "label": "创建时间"},
    {"source": "updated_at", "label": "更新时间"},
    {"source": "conflict_flag", "label": "冲突标记"},
    {"source": "conflict_type", "label": "冲突类型"},
    {"source": "status", "label": "数据状态"},
]

_PRESET_ROLES = [
    {
        "name": "admin",
        "description": "超级管理员，拥有所有权限",
        "permissions": ["*"],
    },
    {
        "name": "annotator",
        "description": "标注员，可查看数据、提交标注、执行导出",
        "permissions": [
            "data:read",
            "annotation:read",
            "annotation:write",
            "pipeline:read",
            "export:read",
            "export:create",
            "config:read",
        ],
    },
    {
        "name": "viewer",
        "description": "只读访问，可查看数据和导出结果",
        "permissions": [
            "data:read",
            "annotation:read",
            "pipeline:read",
            "export:read",
            "config:read",
        ],
    },
]


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
        s = self._Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def seed_defaults(self) -> None:
        """首次启动时写入预置角色和默认数据集（完全幂等，可重复调用）"""
        with self._session() as s:
            # 预置角色（按名称判重）
            for r in _PRESET_ROLES:
                if not s.query(Role).filter(Role.name == r["name"]).first():
                    s.add(
                        Role(
                            name=r["name"],
                            description=r["description"],
                            permissions=r["permissions"],
                            created_at=_now(),
                        )
                    )
            s.flush()  # 确保 roles 有 id 后再操作 dataset

            # 默认数据集（按名称判重）
            if not s.query(Dataset).filter(Dataset.name == "默认数据集").first():
                ds = Dataset(
                    name="默认数据集",
                    description="系统初始化创建的默认数据集",
                    is_active=True,
                    created_at=_now(),
                    updated_at=_now(),
                )
                s.add(ds)
                s.flush()
                s.add(
                    SystemConfig(
                        dataset_id=ds.id,
                        config_data=DEFAULT_DATASET_CONFIG,
                        updated_at=_now(),
                        updated_by="system",
                    )
                )

    # ── User 管理 ──────────────────────────────────────────────────────────────
    def list_users(self) -> list[dict]:
        """List all users."""
        from datapulse.repository.user_repository import UserRepository

        with self._session() as s:
            repo = UserRepository(s)
            return repo.list_users()

    def get_user(self, user_id: int) -> dict | None:
        """Get a user by ID."""
        from datapulse.repository.user_repository import UserRepository

        with self._session() as s:
            repo = UserRepository(s)
            return repo.get(user_id)

    def get_user_by_username(self, username: str) -> dict | None:
        """Get a user by username (includes password_hash for auth)."""
        from datapulse.repository.user_repository import UserRepository

        with self._session() as s:
            repo = UserRepository(s)
            return repo.get_by_username(username)

    def create_user(
        self, username: str, password: str, email: str = "", role_names: list[str] | None = None
    ) -> dict:
        """Create a new user."""
        from datapulse.repository.user_repository import UserRepository

        with self._session() as s:
            repo = UserRepository(s)
            return repo.create(username, password, email, role_names)

    def update_user(self, user_id: int, data: dict) -> dict | None:
        """Update a user."""
        from datapulse.repository.user_repository import UserRepository

        with self._session() as s:
            repo = UserRepository(s)
            return repo.update(user_id, data)

    def delete_user(self, user_id: int) -> bool:
        """Delete a user."""
        from datapulse.repository.user_repository import UserRepository

        with self._session() as s:
            repo = UserRepository(s)
            return repo.delete(user_id)

    def list_roles(self) -> list[dict]:
        """List all roles."""
        from datapulse.repository.user_repository import UserRepository

        with self._session() as s:
            repo = UserRepository(s)
            return repo.list_roles()

    # ── Dataset 管理 ────────────────────────────────────────────────────────────
    def list_datasets(self, include_inactive: bool = False) -> list[dict]:
        """List all datasets."""
        from datapulse.repository.dataset_repository import DatasetRepository

        with self._session() as s:
            repo = DatasetRepository(s)
            return repo.list_datasets(include_inactive=include_inactive)

    def get_dataset(self, dataset_id: int) -> dict | None:
        """Get a dataset by ID."""
        from datapulse.repository.dataset_repository import DatasetRepository

        with self._session() as s:
            repo = DatasetRepository(s)
            return repo.get(dataset_id)

    def create_dataset(self, name: str, description: str = "") -> dict:
        """Create a new dataset."""
        from datapulse.repository.dataset_repository import DatasetRepository

        with self._session() as s:
            repo = DatasetRepository(s)
            return repo.create(name, description)

    def update_dataset(self, dataset_id: int, data: dict) -> dict | None:
        """Update a dataset."""
        from datapulse.repository.dataset_repository import DatasetRepository

        with self._session() as s:
            repo = DatasetRepository(s)
            return repo.update(dataset_id, data)

    def delete_dataset(self, dataset_id: int) -> bool:
        """Delete a dataset."""
        from datapulse.repository.dataset_repository import DatasetRepository

        with self._session() as s:
            repo = DatasetRepository(s)
            return repo.delete(dataset_id)

    # ── Data 管理 ───────────────────────────────────────────────────────────────
    def create_data(self, dataset_id: int, text: str, source_file: str = "") -> dict:
        """Create a new data item."""
        from datapulse.repository.data_repository import DataRepository

        with self._session() as s:
            repo = DataRepository(s)
            return repo.create(dataset_id, text, source_file)

    def get_data(self, item_id: int) -> dict | None:
        """Get a data item by ID."""
        from datapulse.repository.data_repository import DataRepository

        with self._session() as s:
            repo = DataRepository(s)
            return repo.get(item_id)

    def update_data(self, item: dict) -> dict:
        """Update a data item."""
        from datapulse.repository.data_repository import DataRepository

        with self._session() as s:
            repo = DataRepository(s)
            return repo.update(item)

    def delete_data(self, item_id: int) -> bool:
        """Delete a data item."""
        from datapulse.repository.data_repository import DataRepository

        with self._session() as s:
            repo = DataRepository(s)
            return repo.delete(item_id)

    def list_all_data(
        self, dataset_id: int, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> dict:
        """List data items with pagination."""
        from datapulse.repository.data_repository import DataRepository

        with self._session() as s:
            repo = DataRepository(s)
            return repo.list_all(dataset_id, status, page, page_size)

    def list_data_by_status(self, dataset_id: int, status: str) -> list[dict]:
        """List data items by status."""
        from datapulse.repository.data_repository import DataRepository

        with self._session() as s:
            repo = DataRepository(s)
            return repo.list_by_status(dataset_id, status)

    def stats(self, dataset_id: int) -> dict:
        """Get statistics for data items."""
        from datapulse.repository.data_repository import DataRepository

        with self._session() as s:
            repo = DataRepository(s)
            return repo.stats(dataset_id)

    # ── Pipeline 管理 ────────────────────────────────────────────────────────────
    def get_pipeline_status(self, dataset_id: int) -> dict:
        """Get pipeline status for a dataset."""
        from datapulse.repository.pipeline_repository import PipelineRepository

        with self._session() as s:
            repo = PipelineRepository(s)
            return repo.get_status(dataset_id)

    def set_pipeline_status(self, dataset_id: int, data: dict) -> None:
        """Set pipeline status for a dataset."""
        from datapulse.repository.pipeline_repository import PipelineRepository

        with self._session() as s:
            repo = PipelineRepository(s)
            repo.set_status(dataset_id, data)

    # ── Config 管理 ─────────────────────────────────────────────────────────────
    def get_dataset_config(self, dataset_id: int) -> dict:
        """Get dataset configuration."""
        from datapulse.repository.config_repository import ConfigRepository

        with self._session() as s:
            repo = ConfigRepository(s)
            return repo.get_dataset_config(dataset_id)

    def set_dataset_config(self, dataset_id: int, config: dict, updated_by: str) -> None:
        """Set dataset configuration."""
        from datapulse.repository.config_repository import ConfigRepository

        with self._session() as s:
            repo = ConfigRepository(s)
            repo.set_dataset_config(dataset_id, config, updated_by)

    # ── Template 管理 ───────────────────────────────────────────────────────────
    def list_templates(self, dataset_id: int) -> list[dict]:
        """List templates for a dataset."""
        from datapulse.repository.template_repository import TemplateRepository

        with self._session() as s:
            repo = TemplateRepository(s)
            return repo.list_templates(dataset_id)

    def get_template(self, template_id: int) -> dict | None:
        """Get a template by ID."""
        from datapulse.repository.template_repository import TemplateRepository

        with self._session() as s:
            repo = TemplateRepository(s)
            return repo.get(template_id)

    def create_template(self, dataset_id: int, data: dict) -> dict:
        """Create a new template."""
        from datapulse.repository.template_repository import TemplateRepository

        with self._session() as s:
            repo = TemplateRepository(s)
            return repo.create(dataset_id, data)

    def update_template(self, template_id: int, data: dict) -> dict | None:
        """Update a template."""
        from datapulse.repository.template_repository import TemplateRepository

        with self._session() as s:
            repo = TemplateRepository(s)
            return repo.update(template_id, data)

    def delete_template(self, template_id: int) -> bool:
        """Delete a template."""
        from datapulse.repository.template_repository import TemplateRepository

        with self._session() as s:
            repo = TemplateRepository(s)
            return repo.delete(template_id)


# ── 单例 ──────────────────────────────────────────────────────────────────────

_db: DBManager | None = None


def init_db(db_url: str) -> None:
    global _db
    _db = DBManager(db_url)


def get_db() -> DBManager:
    if _db is None:
        raise RuntimeError("DBManager 未初始化，请检查 main.py 中的 init_db() 调用")
    return _db
