"""Data repository — CRUD on t_data_item + t_data_state（联动维护）"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy import exists

from datapulse.model.entities import (
    Annotation, AnnotationResult, Conflict, DataItem, DataState, PreAnnotation,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_STAGES = ["raw", "cleaned", "pre_annotated", "annotated", "checked"]


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _item_to_dict(item: DataItem, state: DataState | None = None) -> dict[str, Any]:
    stage = state.stage if state else item.status
    return {
        "id": item.id,
        "dataset_id": item.dataset_id,
        "content": item.content,
        "content_hash": item.content_hash,
        "source": item.source,
        "source_ref": item.source_ref,
        "status": stage,   # 前端统一读取 status
        "stage": stage,    # 兼容旧调用 & 导出模板
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "created_by": item.created_by,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "updated_by": item.updated_by,
    }


def _enrich(session: Session, base: dict[str, Any], my_username: str | None = None) -> dict[str, Any]:
    """追加最新预标注、有效标注列表、汇总结果、冲突信息。
    my_username: 若提供，则在返回值中附加该用户的标注（my_annotation 字段）。
    """
    data_id = base["id"]

    # ── 最新预标注 ────────────────────────────────────────────────────────────
    pre = (
        session.query(PreAnnotation)
        .filter(PreAnnotation.data_id == data_id)
        .order_by(PreAnnotation.version.desc())
        .first()
    )
    base["model_pred"]  = pre.label if pre else None
    base["model_score"] = float(pre.score) if pre and pre.score is not None else None
    base["model_name"]  = pre.model_name if pre else None
    base["pre_annotation"] = (
        {
            "label":      pre.label,
            "score":      float(pre.score) if pre.score is not None else None,
            "model_name": pre.model_name,
        }
        if pre else None
    )

    # ── 所有有效标注（多人，事实层）──────────────────────────────────────────
    ann_rows = (
        session.query(Annotation)
        .filter(Annotation.data_id == data_id, Annotation.is_active.is_(True))
        .order_by(Annotation.created_at.asc())
        .all()
    )
    annotations = [
        {
            "id":         a.id,
            "username":   a.username,
            "label":      a.label,
            "version":    a.version,
            "is_active":  True,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in ann_rows
    ]
    base["annotations"] = annotations

    # ── 汇总结果（t_annotation_result，用于 DataExplorer / 导出）──────────────
    ann_result = (
        session.query(AnnotationResult)
        .filter(AnnotationResult.data_id == data_id)
        .first()
    )
    final_label     = ann_result.final_label     if ann_result else None
    label_source    = ann_result.label_source    if ann_result else None
    annotator_count = ann_result.annotator_count if ann_result else 0
    resolver        = ann_result.resolver        if ann_result else None

    # label / annotator 字段：优先使用 final_label（来自 t_annotation_result）
    base["label"]           = final_label
    base["label_source"]    = label_source        # "auto" | "manual" | None
    base["annotator_count"] = annotator_count
    base["resolver"]        = resolver
    # 向前兼容：annotator 取第一个有效标注者
    if annotations:
        base["annotator"]    = annotations[0]["username"]
        base["annotated_at"] = annotations[0]["created_at"]
    else:
        base["annotator"]    = None
        base["annotated_at"] = None

    # ── 当前用户自己的标注（可选，标注工作台使用）────────────────────────────
    if my_username:
        my_ann_row = next(
            (a for a in ann_rows if a.username == my_username), None
        )
        base["my_annotation"] = (
            {
                "id":         my_ann_row.id,
                "username":   my_ann_row.username,
                "label":      my_ann_row.label,
                "version":    my_ann_row.version,
                "is_active":  True,
                "created_at": my_ann_row.created_at.isoformat() if my_ann_row.created_at else None,
            }
            if my_ann_row else None
        )
    else:
        base["my_annotation"] = None

    # ── 冲突信息 ──────────────────────────────────────────────────────────────
    open_conflict = (
        session.query(Conflict)
        .filter(Conflict.data_id == data_id, Conflict.status == "open")
        .first()
    )
    base["conflict_flag"]   = open_conflict is not None
    base["conflict_type"]   = open_conflict.conflict_type if open_conflict else None
    base["conflict_detail"] = open_conflict.detail        if open_conflict else None

    return base


class DataRepository:
    """Repository for DataItem + DataState entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── Write ────────────────────────────────────────────────────────────────

    def create(
        self,
        dataset_id: int,
        content: str,
        source: str = "",
        source_ref: str = "",
        created_by: str = "",
    ) -> dict[str, Any] | None:
        """创建数据条目，重复内容（同 dataset + hash）返回 None（跳过）"""
        chash = _content_hash(content)
        existing = (
            self.session.query(DataItem)
            .filter(DataItem.dataset_id == dataset_id, DataItem.content_hash == chash)
            .first()
        )
        if existing:
            return None  # 重复，跳过

        ts = _now()
        item = DataItem(
            dataset_id=dataset_id,
            content=content,
            content_hash=chash,
            source=source,
            source_ref=source_ref,
            status="raw",
            created_at=ts,
            created_by=created_by,
            updated_at=ts,
            updated_by=created_by,
        )
        self.session.add(item)
        self.session.flush()

        state = DataState(
            data_id=item.id,
            stage="raw",
            updated_at=ts,
            updated_by=created_by,
        )
        self.session.add(state)
        return _item_to_dict(item, state)

    def update_stage(self, data_id: int, stage: str, updated_by: str = "") -> None:
        """更新流转阶段（同时更新 t_data_state 和 t_data_item.status）"""
        ts = _now()
        state = self.session.get(DataState, data_id)
        if state is None:
            state = DataState(data_id=data_id, stage=stage, updated_at=ts, updated_by=updated_by)
            self.session.add(state)
        else:
            state.stage = stage
            state.updated_at = ts
            state.updated_by = updated_by

        item = self.session.get(DataItem, data_id)
        if item:
            item.status = stage
            item.updated_at = ts
            item.updated_by = updated_by

    def update_content(self, data_id: int, content: str, updated_by: str = "") -> None:
        """更新文本内容（同步 content_hash）"""
        item = self.session.get(DataItem, data_id)
        if item:
            item.content = content
            item.content_hash = _content_hash(content)
            item.updated_at = _now()
            item.updated_by = updated_by

    def delete(self, item_id: int) -> bool:
        item = self.session.get(DataItem, item_id)
        if item is None:
            return False
        state = self.session.get(DataState, item_id)
        if state:
            self.session.delete(state)
        self.session.delete(item)
        return True

    # ── Read ─────────────────────────────────────────────────────────────────

    def get(self, item_id: int, enrich: bool = True) -> dict[str, Any] | None:
        item = self.session.get(DataItem, item_id)
        if item is None:
            return None
        state = self.session.get(DataState, item_id)
        base = _item_to_dict(item, state)
        return _enrich(self.session, base) if enrich else base

    def list_all(
        self,
        dataset_id: int,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        enrich: bool = True,
    ) -> dict[str, Any]:
        q = self.session.query(DataItem).filter(DataItem.dataset_id == dataset_id)
        if status:
            q = q.filter(DataItem.status == status)
        if keyword:
            q = q.filter(DataItem.content.ilike(f"%{keyword}%"))
        total = q.count()
        rows = (
            q.order_by(DataItem.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = []
        for row in rows:
            state = self.session.get(DataState, row.id)
            base = _item_to_dict(row, state)
            items.append(_enrich(self.session, base) if enrich else base)
        return {"total": total, "page": page, "page_size": page_size, "list": items}

    def list_unannotated_by_user(
        self,
        dataset_id: int,
        username: str,
        page: int = 1,
        page_size: int = 20,
        enrich: bool = True,
    ) -> dict[str, Any]:
        """返回当前用户尚未标注的条目（状态为 pre_annotated 或 annotated）。
        多人标注模式：每位用户独立看到自己未标注的队列，互不干扰。
        """
        # 当前用户已有有效标注的 data_id 集合
        annotated_by_user = (
            self.session.query(Annotation.data_id)
            .filter(
                Annotation.username == username,
                Annotation.is_active.is_(True),
            )
            .subquery()
        )
        q = (
            self.session.query(DataItem)
            .filter(
                DataItem.dataset_id == dataset_id,
                DataItem.status.in_(["pre_annotated", "annotated"]),
                DataItem.id.notin_(self.session.query(annotated_by_user.c.data_id)),
            )
        )
        total = q.count()
        rows = (
            q.order_by(DataItem.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = []
        for row in rows:
            state = self.session.get(DataState, row.id)
            base = _item_to_dict(row, state)
            items.append(_enrich(self.session, base) if enrich else base)
        return {"total": total, "page": page, "page_size": page_size, "list": items}

    def list_annotatable_for_user(
        self,
        dataset_id: int,
        username: str,
        view: str = "all",
        page: int = 1,
        page_size: int = 50,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """标注工作台统一查询：返回 pre_annotated / annotated 的条目，含当前用户的标注。

        view:
          "all"          — 全部条目（含已标注和未标注）
          "unannotated"  — 当前用户尚未标注的条目
          "my_annotated" — 当前用户已标注的条目
        每条记录附加 my_annotation 字段（当前用户的有效标注，或 None）。
        """
        q = self.session.query(DataItem).filter(
            DataItem.dataset_id == dataset_id,
            DataItem.status.in_(["pre_annotated", "annotated"]),
        )
        if keyword:
            q = q.filter(DataItem.content.ilike(f"%{keyword}%"))

        if view in ("unannotated", "my_annotated"):
            user_ann_subq = (
                self.session.query(Annotation.data_id)
                .filter(
                    Annotation.username == username,
                    Annotation.is_active.is_(True),
                )
                .subquery()
            )
            if view == "unannotated":
                q = q.filter(
                    DataItem.id.notin_(self.session.query(user_ann_subq.c.data_id))
                )
            else:  # my_annotated
                q = q.filter(
                    DataItem.id.in_(self.session.query(user_ann_subq.c.data_id))
                )

        total = q.count()
        rows = (
            q.order_by(DataItem.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = []
        for row in rows:
            state = self.session.get(DataState, row.id)
            base  = _item_to_dict(row, state)
            enriched = _enrich(self.session, base, my_username=username)
            items.append(enriched)
        return {"total": total, "page": page, "page_size": page_size, "list": items}

    def list_by_status(
        self, dataset_id: int, stage: str, enrich: bool = False
    ) -> list[dict[str, Any]]:
        """按阶段批量查询（pipeline 内部使用，默认不 enrich 以提升性能）"""
        rows = (
            self.session.query(DataItem)
            .filter(DataItem.dataset_id == dataset_id, DataItem.status == stage)
            .all()
        )
        result = []
        for row in rows:
            state = self.session.get(DataState, row.id)
            base = _item_to_dict(row, state)
            result.append(_enrich(self.session, base) if enrich else base)
        return result

    def stats(self, dataset_id: int) -> dict[str, int]:
        rows = (
            self.session.query(DataItem.status, func.count(DataItem.id))
            .filter(DataItem.dataset_id == dataset_id)
            .group_by(DataItem.status)
            .all()
        )
        result: dict[str, int] = {s: 0 for s in _STAGES}
        result["total"] = 0
        for st, cnt in rows:
            if st in result:
                result[st] = cnt
            result["total"] += cnt
        return result
