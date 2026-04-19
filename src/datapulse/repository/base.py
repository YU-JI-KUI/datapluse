"""Database session management, singleton DBManager, and shared constants."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import create_engine

_log = structlog.get_logger(__name__)
from sqlalchemy.orm import Session, sessionmaker

from datapulse.model.entities import Base, Dataset, Role, SystemConfig

_SHANGHAI = ZoneInfo("Asia/Shanghai")


# ── 密码工具 ──────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    import bcrypt as _bcrypt
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    import bcrypt as _bcrypt
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


# ── 共享常量 ──────────────────────────────────────────────────────────────────

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
        "min_annotation_count": 2,
        "require_cot": True,
    },
    "labels": ["寿险意图", "拒识"],
}

DEFAULT_COLUMNS = [
    {"source": "id",                "target": "id",                "include": True},
    {"source": "content",           "target": "content",           "include": True},
    {"source": "label",             "target": "label",             "include": True},
    {"source": "label_source",      "target": "label_source",      "include": True},
    {"source": "annotator",         "target": "annotator",         "include": True},
    {"source": "annotated_at",      "target": "annotated_at",      "include": True},
    {"source": "annotators",        "target": "annotators",        "include": False},
    {"source": "resolver",          "target": "resolver",          "include": False},
    {"source": "model_pred",        "target": "model_pred",        "include": True},
    {"source": "model_score",       "target": "model_score",       "include": True},
    {"source": "source_ref",        "target": "source_ref",        "include": True},
    {"source": "status",            "target": "status",            "include": True},
    {"source": "created_at",        "target": "created_at",        "include": True},
    {"source": "updated_at",        "target": "updated_at",        "include": False},
    {"source": "result_updated_at", "target": "result_updated_at", "include": False},
]

AVAILABLE_FIELDS = [
    # ── 基础字段 ──────────────────────────────────────────────────────────────
    {"source": "id",                "label": "数据 ID"},
    {"source": "content",           "label": "原始文本"},
    {"source": "source_ref",        "label": "来源文件"},
    {"source": "status",            "label": "数据阶段"},
    {"source": "created_at",        "label": "创建时间"},
    {"source": "updated_at",        "label": "数据更新时间"},
    # ── 最终标注结果（来自 t_annotation_result）────────────────────────────────
    {"source": "label",             "label": "最终标注标签"},
    {"source": "label_source",      "label": "标签来源 (auto/manual)"},
    {"source": "annotated_at",      "label": "标注完成时间"},
    {"source": "result_updated_at", "label": "结果最后更新时间"},
    # ── 标注人员 ──────────────────────────────────────────────────────────────
    {"source": "annotator",         "label": "标注员（裁决者/全部参与者）"},
    {"source": "annotators",        "label": "全部标注员（逗号分隔）"},
    {"source": "annotator_count",   "label": "参与标注人数"},
    {"source": "resolver",          "label": "冲突裁决人"},
    # ── 预标注（模型预测）─────────────────────────────────────────────────────
    {"source": "model_pred",        "label": "模型预测标签"},
    {"source": "model_score",       "label": "模型置信度"},
    {"source": "model_name",        "label": "预测模型名称"},
    # ── 冲突 ──────────────────────────────────────────────────────────────────
    {"source": "conflict_flag",     "label": "是否存在冲突"},
    {"source": "conflict_type",     "label": "冲突类型"},
]

_PRESET_ROLES = [
    {
        "name": "admin",
        "description": "超级管理员，拥有所有权限",
        "permissions": ["*"],
    },
    {
        "name": "annotator",
        "description": "标注员，可查看数据、提交标注、执行导出、运行 Pipeline",
        "permissions": [
            "data:read", "annotation:read", "annotation:write",
            "pipeline:read", "pipeline:run", "export:read", "export:create", "config:read",
        ],
    },
    {
        "name": "viewer",
        "description": "只读访问，可查看数据和导出结果",
        "permissions": [
            "data:read", "annotation:read", "pipeline:read",
            "export:read", "config:read",
        ],
    },
]


# ── DBManager ──────────────────────────────────────────────────────────────────

class DBManager:
    """PostgreSQL 存储管理器（单例），所有 repository 的统一入口"""

    def __init__(self, db_url: str) -> None:
        # 从 url 中提取 host/db 用于日志（不打印密码）
        try:
            from urllib.parse import urlparse
            _p = urlparse(db_url)
            _log.info("DB engine created", host=_p.hostname, port=_p.port, db=_p.path.lstrip("/"))
        except Exception:
            _log.info("DB engine created")
        self._engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
        Base.metadata.create_all(self._engine)
        _log.info("ORM tables synced (CREATE TABLE IF NOT EXISTS)")
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
        """首次启动写入预置角色和默认数据集（完全幂等）。
        角色已存在时也会更新 permissions/description，保证代码变更自动生效。
        """
        with self._session() as s:
            for r in _PRESET_ROLES:
                existing = s.query(Role).filter(Role.name == r["name"]).first()
                if not existing:
                    ts = _now()
                    s.add(Role(
                        name=r["name"],
                        description=r["description"],
                        permissions=r["permissions"],
                        created_at=ts, created_by="system",
                        updated_at=ts, updated_by="system",
                    ))
                else:
                    # 权限或描述有变更时自动同步
                    existing.permissions = r["permissions"]
                    existing.description = r["description"]
                    existing.updated_at  = _now()
                    existing.updated_by  = "system"
            s.flush()

            if not s.query(Dataset).filter(Dataset.name == "默认数据集").first():
                ts = _now()
                ds = Dataset(
                    name="默认数据集",
                    description="系统初始化创建的默认数据集",
                    status="active",
                    created_at=ts, created_by="system",
                    updated_at=ts, updated_by="system",
                )
                s.add(ds)
                s.flush()
                s.add(SystemConfig(
                    dataset_id=ds.id,
                    config_data=DEFAULT_DATASET_CONFIG,
                    updated_at=ts,
                    updated_by="system",
                ))

    # ── User ──────────────────────────────────────────────────────────────────

    def list_users(self, keyword: str | None = None, is_active: bool | None = None,
                   start_date: str | None = None, end_date: str | None = None,
                   page: int = 1, page_size: int = 20) -> dict:
        from datapulse.repository.user_repository import UserRepository
        with self._session() as s:
            return UserRepository(s).list_users(
                keyword=keyword, is_active=is_active,
                start_date=start_date, end_date=end_date,
                page=page, page_size=page_size,
            )

    def get_user(self, user_id: int) -> dict | None:
        from datapulse.repository.user_repository import UserRepository
        with self._session() as s:
            return UserRepository(s).get(user_id)

    def get_user_by_username(self, username: str) -> dict | None:
        from datapulse.repository.user_repository import UserRepository
        with self._session() as s:
            return UserRepository(s).get_by_username(username)

    def create_user(self, username: str, password: str, email: str = "",
                    role_names: list[str] | None = None, created_by: str = "system") -> dict:
        from datapulse.repository.user_repository import UserRepository
        with self._session() as s:
            return UserRepository(s).create(username, password, email, role_names, created_by)

    def update_user(self, user_id: int, data: dict, updated_by: str = "system") -> dict | None:
        from datapulse.repository.user_repository import UserRepository
        with self._session() as s:
            return UserRepository(s).update(user_id, data, updated_by)

    def delete_user(self, user_id: int) -> bool:
        from datapulse.repository.user_repository import UserRepository
        with self._session() as s:
            return UserRepository(s).delete(user_id)

    def update_last_login(self, username: str) -> None:
        from datapulse.repository.user_repository import UserRepository
        with self._session() as s:
            UserRepository(s).update_last_login(username)

    def list_roles(self) -> list[dict]:
        from datapulse.repository.user_repository import UserRepository
        with self._session() as s:
            return UserRepository(s).list_roles()

    # ── Dataset ───────────────────────────────────────────────────────────────

    def list_datasets(self, include_inactive: bool = False) -> list[dict]:
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            return DatasetRepository(s).list_datasets(include_inactive=include_inactive)

    def get_dataset(self, dataset_id: int) -> dict | None:
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            return DatasetRepository(s).get(dataset_id)

    def create_dataset(self, name: str, description: str = "", created_by: str = "system") -> dict:
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            return DatasetRepository(s).create(name, description, created_by)

    def update_dataset(self, dataset_id: int, data: dict, updated_by: str = "system") -> dict | None:
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            return DatasetRepository(s).update(dataset_id, data, updated_by)

    def delete_dataset(self, dataset_id: int) -> bool:
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            return DatasetRepository(s).delete(dataset_id)

    def delete_dataset_cascade(self, dataset_id: int) -> None:
        """后台异步级联删除数据集所有关联数据"""
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            DatasetRepository(s).delete_cascade(dataset_id)

    def list_datasets_for_user(self, username: str, roles: list) -> list[dict]:
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            return DatasetRepository(s).list_datasets_for_user(username, roles)

    def get_assigned_users(self, dataset_id: int) -> list[str]:
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            return DatasetRepository(s).get_assigned_users(dataset_id)

    def assign_users(self, dataset_id: int, usernames: list[str], by: str = "system") -> None:
        from datapulse.repository.dataset_repository import DatasetRepository
        with self._session() as s:
            DatasetRepository(s).assign_users(dataset_id, usernames, by)

    # ── Data ──────────────────────────────────────────────────────────────────

    def create_data(self, dataset_id: int, content: str, source: str = "",
                    source_ref: str = "", created_by: str = "") -> dict | None:
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).create(dataset_id, content, source, source_ref, created_by)

    def bulk_create_data(
        self,
        dataset_id: int,
        texts: list[str],
        source: str = "",
        source_ref: str = "",
        created_by: str = "",
    ) -> dict[str, int]:
        """批量创建数据条目（高性能版，整批在一个事务内完成）。
        返回 {"created": N, "skipped": M}。
        """
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).bulk_create(dataset_id, texts, source, source_ref, created_by)

    def bulk_create_data_with_labels(
        self,
        dataset_id: int,
        rows: list[dict],
        source: str = "",
        source_ref: str = "",
        created_by: str = "",
    ) -> dict[str, int]:
        """批量创建数据，含 label 的行同时写入预标注并推进到 pre_annotated 状态。
        rows: [{"content": str, "label": str | None}, ...]
        返回 {"created": N, "skipped": M, "pre_annotated": K}。
        """
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).bulk_create_with_labels(
                dataset_id, rows, source, source_ref, created_by
            )

    def bulk_update_stage(self, ids: list[int], stage: str, updated_by: str = "") -> None:
        """批量更新数据阶段（pipeline 内部使用，一次 UPDATE 代替 N 次逐行调用）"""
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            DataRepository(s).bulk_update_stage(ids, stage, updated_by)

    def get_data(self, item_id: int, enrich: bool = True) -> dict | None:
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).get(item_id, enrich=enrich)

    def update_stage(self, data_id: int, stage: str, updated_by: str = "") -> None:
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            DataRepository(s).update_stage(data_id, stage, updated_by)

    def delete_data(self, item_id: int) -> bool:
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).delete(item_id)

    def batch_delete_data(self, ids: list[int]) -> int:
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).batch_delete(ids)

    def list_all_data(self, dataset_id: int, status: str | None = None,
                      keyword: str | None = None,
                      start_date: str | None = None, end_date: str | None = None,
                      label: str | None = None,
                      page: int = 1, page_size: int = 20, enrich: bool = True) -> dict:
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).list_all(
                dataset_id, status=status, keyword=keyword,
                start_date=start_date, end_date=end_date,
                label=label,
                page=page, page_size=page_size, enrich=enrich,
            )

    def get_distinct_labels(self, dataset_id: int) -> list[str]:
        """返回该 dataset 中 t_annotation_result 里所有非空的标注标签（去重，升序）"""
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).get_distinct_labels(dataset_id)

    def list_data_by_status(self, dataset_id: int, stage: str, enrich: bool = False) -> list[dict]:
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).list_by_status(dataset_id, stage, enrich)

    def list_unannotated_by_user(self, dataset_id: int, username: str,
                                  page: int = 1, page_size: int = 20) -> dict:
        """多人标注模式：返回当前用户尚未标注的条目（pre_annotated | annotated）"""
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).list_unannotated_by_user(
                dataset_id, username, page, page_size, enrich=True
            )

    def list_annotatable_for_user(
        self,
        dataset_id: int,
        username: str,
        view: str = "all",
        page: int = 1,
        page_size: int = 50,
        keyword: str | None = None,
    ) -> dict:
        """标注工作台：返回 pre_annotated/annotated 条目，含当前用户的标注。
        view: all | unannotated | my_annotated
        """
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).list_annotatable_for_user(
                dataset_id, username, view, page, page_size, keyword
            )

    def stats(self, dataset_id: int) -> dict:
        from datapulse.repository.data_repository import DataRepository
        with self._session() as s:
            return DataRepository(s).stats(dataset_id)

    # ── Annotation ────────────────────────────────────────────────────────────

    def create_annotation(self, data_id: int, username: str, label: str,
                           cot: str | None = None, created_by: str = "") -> dict:
        from datapulse.repository.annotation_repository import AnnotationRepository
        with self._session() as s:
            return AnnotationRepository(s).create_annotation(data_id, username, label, cot=cot, created_by=created_by)

    def get_active_annotations(self, data_id: int) -> list[dict]:
        from datapulse.repository.annotation_repository import AnnotationRepository
        with self._session() as s:
            return AnnotationRepository(s).get_active_annotations(data_id)

    def set_annotation_result_manual(
        self, data_id: int, final_label: str, resolver: str,
        cot: str | None = None, updated_by: str = ""
    ) -> dict:
        """冲突裁决：直接设置 t_annotation_result.final_label，来源标记为 manual。
        t_annotation 中的标注事实保持不变。
        """
        from datapulse.repository.annotation_repository import AnnotationRepository
        with self._session() as s:
            return AnnotationRepository(s).set_manual_result(
                data_id, final_label, resolver, cot=cot, updated_by=updated_by or resolver
            )

    def revoke_user_annotation(self, data_id: int, username: str) -> bool:
        """撤销用户对某条数据的有效标注，若无剩余标注则回滚状态到 pre_annotated。
        revoke_annotation 内部已触发 _recompute_result 更新 t_annotation_result。
        """
        from datapulse.repository.annotation_repository import AnnotationRepository
        with self._session() as s:
            ok = AnnotationRepository(s).revoke_annotation(data_id, username)
            if not ok:
                return False
            # 若该条数据已无任何有效标注，回滚状态到 pre_annotated
            remaining = AnnotationRepository(s).get_active_annotations(data_id)
            if not remaining:
                from datapulse.repository.data_repository import DataRepository
                DataRepository(s).update_stage(data_id, "pre_annotated", updated_by=username)
            return True

    def get_annotation_history(self, data_id: int, username: str | None = None) -> list[dict]:
        from datapulse.repository.annotation_repository import AnnotationRepository
        with self._session() as s:
            return AnnotationRepository(s).get_annotation_history(data_id, username)

    def create_pre_annotation(self, data_id: int, model_name: str, label: str,
                               score: float | None = None, created_by: str = "") -> dict:
        from datapulse.repository.annotation_repository import AnnotationRepository
        with self._session() as s:
            return AnnotationRepository(s).create_pre_annotation(data_id, model_name, label, score, created_by)

    def bulk_create_pre_annotations(self, records: list[dict]) -> int:
        """批量写入预标注（pipeline 专用）"""
        from datapulse.repository.annotation_repository import AnnotationRepository
        with self._session() as s:
            return AnnotationRepository(s).bulk_create_pre_annotations(records)

    def get_latest_pre_annotation(self, data_id: int) -> dict | None:
        from datapulse.repository.annotation_repository import AnnotationRepository
        with self._session() as s:
            return AnnotationRepository(s).get_latest_pre_annotation(data_id)

    # ── Conflict ──────────────────────────────────────────────────────────────

    def create_conflict(self, data_id: int, conflict_type: str, detail: dict,
                        created_by: str = "") -> dict:
        from datapulse.repository.conflict_repository import ConflictRepository
        with self._session() as s:
            return ConflictRepository(s).create(data_id, conflict_type, detail, created_by)

    def clear_conflicts(self, data_id: int) -> None:
        from datapulse.repository.conflict_repository import ConflictRepository
        with self._session() as s:
            ConflictRepository(s).clear_conflicts(data_id)

    def get_open_conflicts(self, data_id: int) -> list[dict]:
        from datapulse.repository.conflict_repository import ConflictRepository
        with self._session() as s:
            return ConflictRepository(s).get_open_conflicts(data_id)

    def list_conflicts_by_dataset(self, dataset_id: int, status: str | None = None) -> list[dict]:
        from datapulse.repository.conflict_repository import ConflictRepository
        with self._session() as s:
            return ConflictRepository(s).list_by_dataset(dataset_id, status)

    def get_conflict_by_id(self, conflict_id: int) -> dict | None:
        from datapulse.repository.conflict_repository import ConflictRepository
        with self._session() as s:
            return ConflictRepository(s).get_by_id(conflict_id)

    def resolve_conflict(self, conflict_id: int) -> bool:
        from datapulse.repository.conflict_repository import ConflictRepository
        with self._session() as s:
            return ConflictRepository(s).resolve(conflict_id)

    # ── Comment ───────────────────────────────────────────────────────────────

    def create_comment(self, data_id: int, username: str, comment: str) -> dict:
        from datapulse.repository.comment_repository import CommentRepository
        with self._session() as s:
            return CommentRepository(s).create(data_id, username, comment)

    def list_comments(self, data_id: int) -> list[dict]:
        from datapulse.repository.comment_repository import CommentRepository
        with self._session() as s:
            return CommentRepository(s).list_by_data(data_id)

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def get_pipeline_status(self, dataset_id: int) -> dict:
        from datapulse.repository.pipeline_repository import PipelineRepository
        with self._session() as s:
            return PipelineRepository(s).get_status(dataset_id)

    def set_pipeline_status(self, dataset_id: int, data: dict) -> None:
        from datapulse.repository.pipeline_repository import PipelineRepository
        with self._session() as s:
            PipelineRepository(s).set_status(dataset_id, data)

    # ── Config ────────────────────────────────────────────────────────────────

    def get_dataset_config(self, dataset_id: int) -> dict:
        from datapulse.repository.config_repository import ConfigRepository
        with self._session() as s:
            return ConfigRepository(s).get_dataset_config(dataset_id)

    def set_dataset_config(self, dataset_id: int, config: dict, updated_by: str = "system") -> None:
        from datapulse.repository.config_repository import ConfigRepository
        with self._session() as s:
            ConfigRepository(s).set_dataset_config(dataset_id, config, updated_by)

    # ── Template ──────────────────────────────────────────────────────────────

    def list_templates(self, dataset_id: int) -> list[dict]:
        from datapulse.repository.template_repository import TemplateRepository
        with self._session() as s:
            return TemplateRepository(s).list_templates(dataset_id)

    def get_template(self, template_id: int) -> dict | None:
        from datapulse.repository.template_repository import TemplateRepository
        with self._session() as s:
            return TemplateRepository(s).get(template_id)

    def create_template(self, dataset_id: int, data: dict, created_by: str = "") -> dict:
        from datapulse.repository.template_repository import TemplateRepository
        with self._session() as s:
            return TemplateRepository(s).create(dataset_id, data, created_by)

    def update_template(self, template_id: int, data: dict, updated_by: str = "") -> dict | None:
        from datapulse.repository.template_repository import TemplateRepository
        with self._session() as s:
            return TemplateRepository(s).update(template_id, data, updated_by)

    def delete_template(self, template_id: int) -> bool:
        from datapulse.repository.template_repository import TemplateRepository
        with self._session() as s:
            return TemplateRepository(s).delete(template_id)


# ── 单例 ──────────────────────────────────────────────────────────────────────

_db: DBManager | None = None


def init_db(db_url: str) -> None:
    global _db
    _db = DBManager(db_url)


def get_db() -> DBManager:
    if _db is None:
        raise RuntimeError("DBManager 未初始化，请检查 main.py 中的 init_db() 调用")
    return _db
