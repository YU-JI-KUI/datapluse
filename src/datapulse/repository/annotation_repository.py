"""Annotation repository — t_annotation + t_pre_annotation + t_annotation_result

写入流程：
  create_annotation / revoke_annotation
      → _recompute_result()      ← 自动维护 t_annotation_result（取最新标注 label）

冲突裁决流程：
  set_manual_result()            ← 直接写入 t_annotation_result（来源 manual）
  不触碰 t_annotation（标注事实不可篡改）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from datapulse.model.entities import Annotation, AnnotationResult, DataItem, PreAnnotation

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


def _ann_to_dict(a: Annotation) -> dict[str, Any]:
    return {
        "id": a.id,
        "data_id": a.data_id,
        "username": a.username,
        "label": a.label,
        "cot": a.cot,
        "version": a.version,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "created_by": a.created_by,
    }


def _result_to_dict(r: AnnotationResult) -> dict[str, Any]:
    return {
        "data_id": r.data_id,
        "final_label": r.final_label,
        "label_source": r.label_source,
        "annotator_count": r.annotator_count,
        "resolver": r.resolver,
        "cot": r.cot,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "updated_by": r.updated_by,
    }


def _pre_to_dict(p: PreAnnotation) -> dict[str, Any]:
    return {
        "id": p.id,
        "data_id": p.data_id,
        "model_name": p.model_name,
        "label": p.label,
        "score": float(p.score) if p.score is not None else None,
        "cot": p.cot,
        "version": p.version,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "created_by": p.created_by,
    }


def _recompute_result(session: Session, data_id: int, updated_by: str = "") -> None:
    """annotation insert / revoke 后同步更新 t_annotation_result：
    • 只要有有效标注，就取 created_at 最新的那条标注的 label 作为 final_label
    • 无论之前 label_source 是 auto 还是 manual，都强制覆盖为当前最新状态
    • 这样 DataExplorer 始终展示最后一次标注更新的 label，而不是过期的人工裁决结果
    """
    # 取所有有效标注，按提交时间降序排列——第一条即为最新
    ann_rows = (
        session.query(Annotation)
        .filter(Annotation.data_id == data_id, Annotation.is_active.is_(True))
        .order_by(Annotation.created_at.desc())
        .all()
    )
    count = len(ann_rows)

    # final_label = 最近一次提交/更新的标注 label；无有效标注时置 None
    final_label = ann_rows[0].label if ann_rows else None

    item = session.get(DataItem, data_id)
    dataset_id = item.dataset_id if item else 0
    ts = _now()

    result = (
        session.query(AnnotationResult)
        .filter(AnnotationResult.data_id == data_id)
        .first()
    )

    if result is None:
        result = AnnotationResult(
            data_id=data_id,
            dataset_id=dataset_id,
            final_label=final_label,
            label_source="auto",
            annotator_count=count,
            updated_at=ts,
            updated_by=updated_by,
        )
        session.add(result)
    else:
        # 任何标注变动都强制更新 final_label，不再因 label_source='manual' 而跳过
        result.final_label     = final_label
        result.label_source    = "auto"
        result.annotator_count = count
        result.updated_at      = ts
        result.updated_by      = updated_by


class AnnotationRepository:
    """Repository for Annotation, PreAnnotation, and AnnotationResult entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── 人工标注 ─────────────────────────────────────────────────────────────

    def create_annotation(
        self,
        data_id: int,
        username: str,
        label: str,
        cot: str | None = None,
        created_by: str = "",
    ) -> dict[str, Any]:
        """提交标注，自动处理版本递增并将旧版本标记为历史，然后触发聚合更新"""
        ts = _now()

        # 将同一用户当前有效版本置为历史
        old_rows = (
            self.session.query(Annotation)
            .filter(
                Annotation.data_id == data_id,
                Annotation.username == username,
                Annotation.is_active.is_(True),
            )
            .all()
        )
        max_ver = 0
        for row in old_rows:
            row.is_active = False
            max_ver = max(max_ver, row.version)

        new_version = max_ver + 1
        ann = Annotation(
            data_id=data_id,
            username=username,
            label=label,
            cot=cot or None,
            version=new_version,
            is_active=True,
            created_at=ts,
            created_by=created_by or username,
        )
        self.session.add(ann)
        self.session.flush()

        # 触发聚合：自动更新 t_annotation_result
        _recompute_result(self.session, data_id, updated_by=created_by or username)

        return _ann_to_dict(ann)

    def revoke_annotation(self, data_id: int, username: str) -> bool:
        """撤销用户对某条数据的当前有效标注，返回 True 表示成功撤销，然后触发聚合更新"""
        rows = (
            self.session.query(Annotation)
            .filter(
                Annotation.data_id == data_id,
                Annotation.username == username,
                Annotation.is_active.is_(True),
            )
            .all()
        )
        if not rows:
            return False
        for row in rows:
            row.is_active = False

        # 触发聚合：重新计算最终标签
        _recompute_result(self.session, data_id, updated_by=username)
        return True

    def set_manual_result(
        self,
        data_id: int,
        final_label: str,
        resolver: str,
        cot: str | None = None,
        updated_by: str = "",
    ) -> dict[str, Any]:
        """冲突裁决专用：直接设置最终标注标签，来源标记为 manual。
        t_annotation 中的标注事实不受影响。
        """
        item = self.session.get(DataItem, data_id)
        dataset_id = item.dataset_id if item else 0
        ts = _now()

        # 统计当前有效标注人数
        count = (
            self.session.query(Annotation)
            .filter(Annotation.data_id == data_id, Annotation.is_active.is_(True))
            .count()
        )

        result = (
            self.session.query(AnnotationResult)
            .filter(AnnotationResult.data_id == data_id)
            .first()
        )

        if result is None:
            result = AnnotationResult(
                data_id=data_id,
                dataset_id=dataset_id,
                final_label=final_label,
                label_source="manual",
                annotator_count=count,
                resolver=resolver,
                cot=cot or None,
                updated_at=ts,
                updated_by=updated_by or resolver,
            )
            self.session.add(result)
        else:
            result.final_label = final_label
            result.label_source = "manual"
            result.annotator_count = count
            result.resolver = resolver
            result.cot = cot or None
            result.updated_at = ts
            result.updated_by = updated_by or resolver

        self.session.flush()
        return _result_to_dict(result)

    def bulk_set_manual_result(
        self,
        data_ids: list[int],
        final_label: str,
        resolver: str,
        cot: str | None = None,
        updated_by: str = "",
    ) -> None:
        """批量冲突裁决：为一组 data_id 设置相同的最终标签（manual 来源）。

        3 次 IN 查询 + 1 次 bulk INSERT（如需新建 AnnotationResult），
        替代 N × set_manual_result 的 N×3 查询。
        """
        if not data_ids:
            return
        ts = _now()
        ub = updated_by or resolver

        # 批量取 dataset_id
        item_rows = (
            self.session.query(DataItem.id, DataItem.dataset_id)
            .filter(DataItem.id.in_(data_ids))
            .all()
        )
        dataset_by_id = {r.id: r.dataset_id for r in item_rows}

        # 批量计算每条 data_id 的有效标注人数
        count_rows = (
            self.session.query(Annotation.data_id, func.count(Annotation.id))
            .filter(Annotation.data_id.in_(data_ids), Annotation.is_active.is_(True))
            .group_by(Annotation.data_id)
            .all()
        )
        count_by_id = {r[0]: r[1] for r in count_rows}

        # 批量取现有 AnnotationResult（UPDATE 路径）
        existing_rows = (
            self.session.query(AnnotationResult)
            .filter(AnnotationResult.data_id.in_(data_ids))
            .all()
        )
        existing_by_id = {r.data_id: r for r in existing_rows}

        # UPDATE existing rows（SQLAlchemy 变更追踪，flush 时批量 UPDATE）
        new_records: list[dict] = []
        for data_id in data_ids:
            count = count_by_id.get(data_id, 0)
            if data_id in existing_by_id:
                r = existing_by_id[data_id]
                r.final_label     = final_label
                r.label_source    = "manual"
                r.annotator_count = count
                r.resolver        = resolver
                r.cot             = cot or None
                r.updated_at      = ts
                r.updated_by      = ub
            else:
                new_records.append({
                    "data_id":        data_id,
                    "dataset_id":     dataset_by_id.get(data_id, 0),
                    "final_label":    final_label,
                    "label_source":   "manual",
                    "annotator_count": count,
                    "resolver":       resolver,
                    "cot":            cot or None,
                    "updated_at":     ts,
                    "updated_by":     ub,
                })

        if new_records:
            self.session.bulk_insert_mappings(AnnotationResult, new_records)

    def get_annotation_result(self, data_id: int) -> dict[str, Any] | None:
        """获取某条数据的汇总结果"""
        result = (
            self.session.query(AnnotationResult)
            .filter(AnnotationResult.data_id == data_id)
            .first()
        )
        return _result_to_dict(result) if result else None

    def get_active_annotations(self, data_id: int) -> list[dict[str, Any]]:
        """获取某条数据所有标注人的当前有效标注"""
        rows = (
            self.session.query(Annotation)
            .filter(Annotation.data_id == data_id, Annotation.is_active.is_(True))
            .order_by(Annotation.created_at.asc())
            .all()
        )
        return [_ann_to_dict(r) for r in rows]

    def get_annotation_history(self, data_id: int, username: str | None = None) -> list[dict[str, Any]]:
        """获取标注历史（含历史版本）"""
        q = self.session.query(Annotation).filter(Annotation.data_id == data_id)
        if username:
            q = q.filter(Annotation.username == username)
        rows = q.order_by(Annotation.version.desc()).all()
        return [_ann_to_dict(r) for r in rows]

    def list_annotations_by_data(self, data_id: int) -> list[dict[str, Any]]:
        """获取某条数据的所有标注（仅有效版本）"""
        return self.get_active_annotations(data_id)

    # ── LLM 预标注 ───────────────────────────────────────────────────────────

    def create_pre_annotation(
        self,
        data_id: int,
        model_name: str,
        label: str,
        score: float | None = None,
        cot: str | None = None,
        created_by: str = "",
    ) -> dict[str, Any]:
        """创建预标注记录，版本号自动递增"""
        latest = (
            self.session.query(PreAnnotation)
            .filter(PreAnnotation.data_id == data_id)
            .order_by(PreAnnotation.version.desc())
            .first()
        )
        version = (latest.version + 1) if latest else 1
        ts = _now()
        pre = PreAnnotation(
            data_id=data_id,
            model_name=model_name,
            label=label,
            score=score,
            cot=cot or None,
            version=version,
            created_at=ts,
            created_by=created_by,
        )
        self.session.add(pre)
        self.session.flush()
        return _pre_to_dict(pre)

    def bulk_create_pre_annotations(
        self,
        records: list[dict],
    ) -> int:
        """批量写入预标注（pipeline 专用）。
        records: [{"data_id": int, "model_name": str, "label": str, "score": float, "created_by": str}, ...]
        版本统一设为 1（pipeline 首次运行），若已存在则跳过（重跑时会重复，可接受）。
        返回实际插入条数。
        """
        if not records:
            return 0
        ts = _now()
        mappings = [
            {
                "data_id":    r["data_id"],
                "model_name": r["model_name"],
                "label":      r["label"],
                "score":      r.get("score"),
                "cot":        r.get("cot") or None,
                "version":    1,
                "created_at": ts,
                "created_by": r.get("created_by", "pipeline"),
            }
            for r in records
        ]
        self.session.bulk_insert_mappings(PreAnnotation, mappings)
        return len(mappings)

    def get_latest_pre_annotation(self, data_id: int) -> dict[str, Any] | None:
        row = (
            self.session.query(PreAnnotation)
            .filter(PreAnnotation.data_id == data_id)
            .order_by(PreAnnotation.version.desc())
            .first()
        )
        return _pre_to_dict(row) if row else None

    def list_pre_annotations(self, data_id: int) -> list[dict[str, Any]]:
        rows = (
            self.session.query(PreAnnotation)
            .filter(PreAnnotation.data_id == data_id)
            .order_by(PreAnnotation.version.desc())
            .all()
        )
        return [_pre_to_dict(r) for r in rows]
