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


# ── 单例 ──────────────────────────────────────────────────────────────────────

_db: DBManager | None = None


def init_db(db_url: str) -> None:
    global _db
    _db = DBManager(db_url)


def get_db() -> DBManager:
    if _db is None:
        raise RuntimeError("DBManager 未初始化，请检查 main.py 中的 init_db() 调用")
    return _db
