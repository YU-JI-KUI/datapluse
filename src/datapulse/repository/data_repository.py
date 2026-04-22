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
    Annotation, AnnotationResult, Conflict, DataComment, DataItem, DataState, PreAnnotation,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_STAGES = ["raw", "cleaned", "pre_annotated", "annotated", "checked"]


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _fetch_state_map(session: Session, ids: list[int]) -> dict[int, DataState]:
    """一次 IN 查询批量拉取 DataState，消除 N+1。
    DataItem.status 与 DataState.stage 始终同步（update_stage 双写），
    两者等价——此函数仅在需要完整 DataState 对象时使用。
    """
    if not ids:
        return {}
    rows = session.query(DataState).filter(DataState.data_id.in_(ids)).all()
    return {s.data_id: s for s in rows}


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


def _enrich_pre_annotation(session: Session, data_id: int, base: dict[str, Any]) -> None:
    """填充最新预标注字段（model_pred / model_score / model_name / pre_annotation）。"""
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
            "cot":        pre.cot,
        }
        if pre else None
    )


def _resolve_annotator_info(
    ann_result: AnnotationResult | None,
    label_source: str | None,
    resolver: str | None,
    annotations: list[dict[str, Any]],
    base: dict[str, Any],
) -> None:
    """填充 annotator / annotated_at 字段，优先使用汇总结果，否则回退到第一条标注。"""
    if ann_result:
        is_manual = label_source == "manual" and resolver
        base["annotator"]    = resolver if is_manual else base["annotators"]
        base["annotated_at"] = base["result_updated_at"]
    elif annotations:
        base["annotator"]    = annotations[0]["username"]
        base["annotated_at"] = annotations[0]["created_at"]
    else:
        base["annotator"]    = None
        base["annotated_at"] = None


def _enrich_annotation_result(
    session: Session,
    data_id: int,
    base: dict[str, Any],
    annotations: list[dict[str, Any]],
) -> None:
    """填充汇总标注结果字段（label / label_source / annotator / annotated_at 等）。"""
    ann_result = (
        session.query(AnnotationResult)
        .filter(AnnotationResult.data_id == data_id)
        .first()
    )

    final_label = label_source = resolver = None
    annotator_count = 0
    result_cot = result_updated_at = None

    if ann_result:
        final_label       = ann_result.final_label
        label_source      = ann_result.label_source
        annotator_count   = ann_result.annotator_count or 0
        resolver          = ann_result.resolver
        result_cot        = ann_result.cot
        result_updated_at = (
            ann_result.updated_at.isoformat() if ann_result.updated_at else None
        )

    base["label"]             = final_label
    base["label_source"]      = label_source        # "auto" | "manual" | None
    base["annotator_count"]   = annotator_count
    base["resolver"]          = resolver
    base["result_cot"]        = result_cot
    base["result_updated_at"] = result_updated_at
    base["annotators"]        = ", ".join(a["username"] for a in annotations) if annotations else None

    _resolve_annotator_info(ann_result, label_source, resolver, annotations, base)


def _enrich_my_annotation(
    ann_rows: list[Annotation],
    my_username: str,
    base: dict[str, Any],
) -> None:
    """填充 my_annotation 字段（标注工作台专用）。"""
    my_ann_row = next((a for a in ann_rows if a.username == my_username), None)
    base["my_annotation"] = (
        {
            "id":         my_ann_row.id,
            "username":   my_ann_row.username,
            "label":      my_ann_row.label,
            "cot":        my_ann_row.cot,
            "version":    my_ann_row.version,
            "is_active":  True,
            "created_at": my_ann_row.created_at.isoformat() if my_ann_row.created_at else None,
        }
        if my_ann_row else None
    )


def _enrich_conflict(session: Session, data_id: int, base: dict[str, Any]) -> None:
    """填充冲突信息字段（conflict_flag / conflict_type / conflict_detail）。"""
    open_conflict = (
        session.query(Conflict)
        .filter(Conflict.data_id == data_id, Conflict.status == "open")
        .first()
    )
    base["conflict_flag"]   = open_conflict is not None
    base["conflict_type"]   = open_conflict.conflict_type if open_conflict else None
    base["conflict_detail"] = open_conflict.detail        if open_conflict else None


def _enrich(session: Session, base: dict[str, Any], my_username: str | None = None) -> dict[str, Any]:
    """追加最新预标注、有效标注列表、汇总结果、冲突信息。
    my_username: 若提供，则在返回值中附加该用户的标注（my_annotation 字段）。
    """
    data_id = base["id"]

    _enrich_pre_annotation(session, data_id, base)

    ann_rows = (
        session.query(Annotation)
        .filter(Annotation.data_id == data_id, Annotation.is_active.is_(True))
        .order_by(Annotation.created_at.asc())
        .all()
    )
    base["annotations"] = [
        {
            "id":         a.id,
            "username":   a.username,
            "label":      a.label,
            "cot":        a.cot,
            "version":    a.version,
            "is_active":  True,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in ann_rows
    ]

    _enrich_annotation_result(session, data_id, base, base["annotations"])

    if my_username:
        _enrich_my_annotation(ann_rows, my_username, base)
    else:
        base["my_annotation"] = None

    _enrich_conflict(session, data_id, base)
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

    def batch_delete(self, ids: list[int]) -> int:
        """批量删除数据条目（同时删除关联的 DataState 记录）"""
        if not ids:
            return 0
        items = self.session.query(DataItem).filter(DataItem.id.in_(ids)).all()
        self.session.query(DataState).filter(DataState.data_id.in_(ids)).delete(synchronize_session=False)
        for item in items:
            self.session.delete(item)
        return len(items)

    def bulk_create(
        self,
        dataset_id: int,
        texts: list[str],
        source: str = "",
        source_ref: str = "",
        created_by: str = "",
    ) -> dict[str, int]:
        """批量创建数据条目，性能优化版：3 次 DB 操作代替 N×4 次。

        步骤：
          1. 一次查询取出该 dataset 已有的全部 content_hash
          2. Python 层过滤重复，得到真正要插入的新记录
          3. bulk_insert_mappings 批量写入 t_data_item（一次 INSERT，无逐行 flush）
          4. 查回新插入行的 id（按 hash 过滤）
          5. bulk_insert_mappings 批量写入 t_data_state
        """
        if not texts:
            return {"created": 0, "skipped": 0}

        ts = _now()

        # ── Step 1: 取出已有 hash 集合（一次 SELECT）──────────────────────────
        hash_pairs = [(t, _content_hash(t)) for t in texts]
        all_hashes = [h for _, h in hash_pairs]

        existing_hashes: set[str] = {
            row[0]
            for row in self.session.query(DataItem.content_hash)
            .filter(
                DataItem.dataset_id == dataset_id,
                DataItem.content_hash.in_(all_hashes),
            )
            .all()
        }

        # ── Step 2: 过滤出新记录，hash 去重（同文件内部也可能重复）────────────
        seen: set[str] = set(existing_hashes)
        new_records: list[dict] = []
        new_hashes:  list[str] = []
        skipped = 0
        for text, chash in hash_pairs:
            if chash in seen:
                skipped += 1
            else:
                seen.add(chash)
                new_records.append({
                    "dataset_id":   dataset_id,
                    "content":      text,
                    "content_hash": chash,
                    "source":       source,
                    "source_ref":   source_ref,
                    "status":       "raw",
                    "created_at":   ts,
                    "created_by":   created_by,
                    "updated_at":   ts,
                    "updated_by":   created_by,
                })
                new_hashes.append(chash)

        if not new_records:
            return {"created": 0, "skipped": skipped}

        # ── Step 3: 批量插入 t_data_item（一次 INSERT）───────────────────────
        self.session.bulk_insert_mappings(DataItem, new_records)
        self.session.flush()

        # ── Step 4: 查回刚插入的 id（一次 SELECT IN）─────────────────────────
        inserted_rows = (
            self.session.query(DataItem.id)
            .filter(
                DataItem.dataset_id == dataset_id,
                DataItem.content_hash.in_(new_hashes),
            )
            .all()
        )

        # ── Step 5: 批量插入 t_data_state（一次 INSERT）──────────────────────
        state_records = [
            {"data_id": row[0], "stage": "raw", "updated_at": ts, "updated_by": created_by}
            for row in inserted_rows
        ]
        self.session.bulk_insert_mappings(DataState, state_records)

        return {"created": len(new_records), "skipped": skipped}

    def bulk_create_with_labels(
        self,
        dataset_id: int,
        rows: list[dict],
        source: str = "",
        source_ref: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        """批量创建带标注的历史数据，单事务完成以下写入：

        有 label 的行：
          - t_data_item / t_data_state → status = annotated
          - t_annotation              → is_active=True, username=created_by, cot=迁移说明
          - t_annotation_result       → label_source="manual", annotator_count=1
          - t_data_comment            → 记录历史数据迁移来源

        无 label 的行：
          - t_data_item / t_data_state → status = raw（原始行为，等待 pipeline）

        rows: [{"content": str, "label": str | None}, ...]
        返回: {"created": N, "skipped": M, "annotated": K}
        """
        from datapulse.modules.processing import _MIGRATION_COT

        if not rows:
            return {"created": 0, "skipped": 0, "annotated": 0}

        ts = _now()
        MIGRATOR = created_by or "system"

        # label_by_hash: content_hash → label（仅有非空 label 的行）
        label_by_hash: dict[str, str] = {}
        for row in rows:
            lbl = (row.get("label") or "").strip()
            if lbl:
                label_by_hash[_content_hash(row["content"])] = lbl

        # ── Step 1: 取出已有 hash ──────────────────────────────────────────
        hash_pairs = [(row["content"], _content_hash(row["content"])) for row in rows]
        all_hashes = [h for _, h in hash_pairs]
        existing_hashes: set[str] = {
            r[0]
            for r in self.session.query(DataItem.content_hash)
            .filter(DataItem.dataset_id == dataset_id, DataItem.content_hash.in_(all_hashes))
            .all()
        }

        # ── Step 2: 过滤新记录 ────────────────────────────────────────────
        seen: set[str] = set(existing_hashes)
        new_records: list[dict] = []
        new_hashes: list[str]   = []
        skipped = 0
        for text, chash in hash_pairs:
            if chash in seen:
                skipped += 1
                continue
            seen.add(chash)
            initial_stage = "annotated" if chash in label_by_hash else "raw"
            new_records.append({
                "dataset_id":   dataset_id,
                "content":      text,
                "content_hash": chash,
                "source":       source,
                "source_ref":   source_ref,
                "status":       initial_stage,
                "created_at":   ts,
                "created_by":   created_by,
                "updated_at":   ts,
                "updated_by":   created_by,
            })
            new_hashes.append(chash)

        if not new_records:
            return {"created": 0, "skipped": skipped, "annotated": 0}

        # ── Step 3: 批量插入 t_data_item ──────────────────────────────────
        self.session.bulk_insert_mappings(DataItem, new_records)
        self.session.flush()

        # ── Step 4: 查回新 id（content_hash → data_id）───────────────────
        inserted = (
            self.session.query(DataItem.id, DataItem.content_hash)
            .filter(DataItem.dataset_id == dataset_id, DataItem.content_hash.in_(new_hashes))
            .all()
        )
        hash_to_id: dict[str, int] = {r.content_hash: r.id for r in inserted}

        # ── Step 5: 批量插入 t_data_state ────────────────────────────────
        state_records = [
            {
                "data_id":    hash_to_id[h],
                "stage":      "annotated" if h in label_by_hash else "raw",
                "updated_at": ts,
                "updated_by": created_by,
            }
            for h in new_hashes if h in hash_to_id
        ]
        self.session.bulk_insert_mappings(DataState, state_records)

        # ── 以下仅处理有 label 的条目 ─────────────────────────────────────
        labeled_ids: list[tuple[int, str]] = [
            (hash_to_id[h], label_by_hash[h])
            for h in new_hashes
            if h in label_by_hash and h in hash_to_id
        ]

        if labeled_ids:
            # ── Step 6: 批量插入 t_annotation（标注事实）────────────────
            ann_records = [
                {
                    "data_id":    data_id,
                    "username":   MIGRATOR,
                    "label":      label,
                    "cot":        _MIGRATION_COT,
                    "version":    1,
                    "is_active":  True,
                    "created_at": ts,
                    "created_by": MIGRATOR,
                }
                for data_id, label in labeled_ids
            ]
            self.session.bulk_insert_mappings(Annotation, ann_records)

            # ── Step 7: 批量插入 t_annotation_result（最终标注结果）──────
            result_records = [
                {
                    "data_id":        data_id,
                    "dataset_id":     dataset_id,
                    "final_label":    label,
                    "label_source":   "manual",
                    "annotator_count": 1,
                    "resolver":       MIGRATOR,
                    "cot":            _MIGRATION_COT,
                    "updated_at":     ts,
                    "updated_by":     MIGRATOR,
                }
                for data_id, label in labeled_ids
            ]
            self.session.bulk_insert_mappings(AnnotationResult, result_records)

            # ── Step 8: 批量插入 t_data_comment（迁移溯源记录）──────────
            comment_text = f"[历史数据迁移] 来源：{source_ref or source or '文件上传'}，标注人：{MIGRATOR}"
            comment_records = [
                {
                    "data_id":    data_id,
                    "username":   MIGRATOR,
                    "comment":    comment_text,
                    "created_at": ts,
                    "created_by": MIGRATOR,
                }
                for data_id, _ in labeled_ids
            ]
            self.session.bulk_insert_mappings(DataComment, comment_records)

        return {
            "created":   len(new_records),
            "skipped":   skipped,
            "annotated": len(labeled_ids),
        }

    def bulk_update_stage(
        self,
        ids: list[int],
        stage: str,
        updated_by: str = "",
    ) -> None:
        """批量更新 stage（一次 UPDATE 代替 N 次逐行 update_stage）。
        用于 pipeline 各步骤结束后统一变更数据状态。
        """
        if not ids:
            return
        ts = _now()
        # 更新 t_data_item.status（支持快速过滤）
        self.session.query(DataItem).filter(DataItem.id.in_(ids)).update(
            {"status": stage, "updated_at": ts, "updated_by": updated_by},
            synchronize_session=False,
        )
        # 更新 t_data_state.stage（控制流）
        self.session.query(DataState).filter(DataState.data_id.in_(ids)).update(
            {"stage": stage, "updated_at": ts, "updated_by": updated_by},
            synchronize_session=False,
        )

    def get_next_pre_annotated(self, dataset_id: int) -> dict[str, Any] | None:
        """取创建时间最早的 pre_annotated 条目并完整 enrich（1+4 次查询，不扫描全表）。"""
        row = (
            self.session.query(DataItem)
            .filter(DataItem.dataset_id == dataset_id, DataItem.status == "pre_annotated")
            .order_by(DataItem.created_at.asc())
            .first()
        )
        if row is None:
            return None
        state = self.session.get(DataState, row.id)
        base = _item_to_dict(row, state)
        return _enrich(self.session, base)

    def enrich_for_conflict(self, items: list[dict[str, Any]]) -> None:
        """为冲突检测批量填充 annotations 和 label 字段（就地修改）。

        仅需 2 次 DB 查询（IN 查询），彻底消除逐条 enrich 的 N×4 查询开销。
        冲突检测只需要：
          - annotations[]：用于 label_conflict（多人标注分歧）
          - label：final_label，用于 semantic_conflict（语义相似但标签不同）
          - label_source：用于自检排除 manual 裁决数据
        不需要：PreAnnotation、Conflict、annotator、my_annotation 等字段。
        """
        if not items:
            return
        ids = [item["id"] for item in items]

        # 批量加载有效标注（annotations 字段）
        ann_rows = (
            self.session.query(Annotation)
            .filter(Annotation.data_id.in_(ids), Annotation.is_active.is_(True))
            .all()
        )
        anns_map: dict[int, list[dict[str, Any]]] = {}
        for a in ann_rows:
            anns_map.setdefault(a.data_id, []).append({
                "id":       a.id,
                "username": a.username,
                "label":    a.label,
                "is_active": True,
            })

        # 批量加载最终标注结果（label / label_source 字段）
        result_rows = (
            self.session.query(AnnotationResult)
            .filter(AnnotationResult.data_id.in_(ids))
            .all()
        )
        result_map = {r.data_id: r for r in result_rows}

        for item in items:
            data_id    = item["id"]
            ann_result = result_map.get(data_id)
            item["annotations"] = anns_map.get(data_id, [])
            item["label"]       = ann_result.final_label  if ann_result else None
            item["label_source"] = ann_result.label_source if ann_result else None

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
        start_date: str | None = None,
        end_date: str | None = None,
        label: str | None = None,
        page: int = 1,
        page_size: int = 20,
        enrich: bool = True,
    ) -> dict[str, Any]:
        q = self.session.query(DataItem).filter(DataItem.dataset_id == dataset_id)
        if status:
            q = q.filter(DataItem.status == status)
        if keyword:
            q = q.filter(DataItem.content.ilike(f"%{keyword}%"))
        if start_date:
            q = q.filter(DataItem.updated_at >= start_date)
        if end_date:
            q = q.filter(DataItem.updated_at <= end_date + " 23:59:59")
        if label:
            q = q.join(
                AnnotationResult,
                AnnotationResult.data_id == DataItem.id,
            ).filter(AnnotationResult.final_label == label)
        total = q.count()
        rows = (
            q.order_by(DataItem.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        state_map = _fetch_state_map(self.session, [r.id for r in rows])
        items = []
        for row in rows:
            base = _item_to_dict(row, state_map.get(row.id))
            items.append(_enrich(self.session, base) if enrich else base)
        return {"total": total, "page": page, "page_size": page_size, "list": items}

    def get_distinct_labels(self, dataset_id: int) -> list[str]:
        """返回该 dataset 中 t_annotation_result 里所有非空的 final_label（去重，升序）"""
        rows = (
            self.session.query(AnnotationResult.final_label)
            .join(DataItem, DataItem.id == AnnotationResult.data_id)
            .filter(
                DataItem.dataset_id == dataset_id,
                AnnotationResult.final_label.isnot(None),
            )
            .distinct()
            .order_by(AnnotationResult.final_label)
            .all()
        )
        return [row[0] for row in rows]

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
        state_map = _fetch_state_map(self.session, [r.id for r in rows])
        items = []
        for row in rows:
            base = _item_to_dict(row, state_map.get(row.id))
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
        label: str | None = None,
    ) -> dict[str, Any]:
        """标注工作台统一查询：返回 pre_annotated / annotated 的条目，含当前用户的标注。

        view:
          "all"          — 全部条目（含已标注和未标注）
          "unannotated"  — 当前用户尚未标注的条目
          "my_annotated" — 当前用户已标注的条目（按自己的标注时间倒序）
        每条记录附加 my_annotation 字段（当前用户的有效标注，或 None）。
        label: 仅对 my_annotated 生效，按用户自己的标注标签过滤。
        """
        from sqlalchemy import and_
        from sqlalchemy.orm import aliased

        q = self.session.query(DataItem).filter(
            DataItem.dataset_id == dataset_id,
            DataItem.status.in_(["pre_annotated", "annotated"]),
        )
        if keyword:
            q = q.filter(DataItem.content.ilike(f"%{keyword}%"))

        if view == "unannotated":
            user_ann_subq = (
                self.session.query(Annotation.data_id)
                .filter(
                    Annotation.username == username,
                    Annotation.is_active.is_(True),
                )
                .subquery()
            )
            q = q.filter(DataItem.id.notin_(self.session.query(user_ann_subq.c.data_id)))
            total = q.count()
            rows  = (
                q.order_by(DataItem.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )

        elif view == "my_annotated":
            # JOIN Annotation 以便按标注时间排序和按标签过滤
            ann_alias = aliased(Annotation)
            q = q.join(
                ann_alias,
                and_(
                    ann_alias.data_id    == DataItem.id,
                    ann_alias.username   == username,
                    ann_alias.is_active.is_(True),
                ),
            )
            if label:
                q = q.filter(ann_alias.label == label)
            total = q.count()
            rows  = (
                q.order_by(ann_alias.created_at.desc())   # 最近标注的排在最前面
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )

        else:  # "all"
            total = q.count()
            rows  = (
                q.order_by(DataItem.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )

        state_map = _fetch_state_map(self.session, [r.id for r in rows])
        items = []
        for row in rows:
            base = _item_to_dict(row, state_map.get(row.id))
            items.append(_enrich(self.session, base, my_username=username))
        return {"total": total, "page": page, "page_size": page_size, "list": items}

    def list_by_status(
        self, dataset_id: int, stage: str, enrich: bool = False
    ) -> list[dict[str, Any]]:
        """按阶段批量查询（pipeline 内部使用，默认不 enrich 以提升性能）。

        DataItem.status 与 DataState.stage 始终双写保持同步，
        _item_to_dict 传 None 时自动回退到 item.status，无需逐行查 DataState。
        """
        rows = (
            self.session.query(DataItem)
            .filter(DataItem.dataset_id == dataset_id, DataItem.status == stage)
            .all()
        )
        if not enrich:
            # 高性能路径：仅 1 次 DB 查询，100k 行也不会 N+1
            return [_item_to_dict(row) for row in rows]

        # enrich=True 时仍需批量拉 DataState（_item_to_dict 需要精确 stage 字段）
        state_map = _fetch_state_map(self.session, [r.id for r in rows])
        return [
            _enrich(self.session, _item_to_dict(row, state_map.get(row.id)))
            for row in rows
        ]

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
