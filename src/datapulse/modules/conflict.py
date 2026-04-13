"""
冲突检测模块（核心）

两种冲突类型：
1. 标注冲突（label_conflict）：同一数据被不同标注员赋予不同标签
2. 语义冲突（semantic_conflict）：语义高度相似（cosine > threshold）但标签不同

结果写入 t_conflict 表（不再写回 t_data_item）。
干净数据的 stage → checked，有冲突数据保持 annotated。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from datapulse.modules.embedding import embed_text
from datapulse.modules.vector import get_index
from datapulse.repository.base import get_db
from datapulse.repository.embeddings import get_emb


# ── 标注冲突检测 ───────────────────────────────────────────────────────────────


def detect_label_conflicts(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """
    同一数据条目，多位标注人给出不同标签 → label_conflict
    返回 {data_id: conflict_detail}
    """
    conflicts: dict[int, dict[str, Any]] = {}
    for item in items:
        annotations = item.get("annotations", [])
        if len(annotations) < 2:
            continue
        labels = {a["label"] for a in annotations}
        if len(labels) > 1:
            conflicts[item["id"]] = {
                "content": item.get("content", ""),
                "conflicting_labels": list(labels),
                "annotators": [
                    {"username": a["username"], "label": a["label"]}
                    for a in annotations
                ],
            }
    return conflicts


# ── 语义冲突检测 ───────────────────────────────────────────────────────────────


def detect_semantic_conflicts(
    items: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """
    语义相似度 > threshold 且标签不同 → semantic_conflict
    返回 {data_id: conflict_detail}
    """
    sim_cfg   = cfg.get("similarity", {})
    threshold = sim_cfg.get("threshold_high", 0.9)
    topk      = sim_cfg.get("topk", 5)

    # 只处理有标注的数据（取第一个有效标注作为代表标签）
    labeled = [i for i in items if i.get("label") is not None]
    if len(labeled) < 2:
        return {}

    emb   = get_emb()
    index = get_index()

    conflict_pairs: set[tuple[int, int]] = set()
    conflicts: dict[int, dict[str, Any]] = {}

    for item in labeled:
        item_id    = item["id"]
        item_label = item["label"]

        vec = emb.load(item_id)
        if vec is None:
            vec = embed_text(item["content"], cfg)
            emb.save(item_id, vec)

        if index.size == 0:
            continue

        for neighbor_id, sim in index.search(vec, topk=topk + 1):
            if neighbor_id == item_id or sim < threshold:
                continue
            neighbor = next((i for i in labeled if i["id"] == neighbor_id), None)
            if neighbor is None or neighbor.get("label") == item_label:
                continue

            pair = tuple(sorted([item_id, neighbor_id]))
            if pair in conflict_pairs:
                continue
            conflict_pairs.add(pair)

            for self_item, other_item in [(item, neighbor), (neighbor, item)]:
                detail = {
                    "similarity": round(sim, 4),
                    "threshold": threshold,
                    "paired_id": other_item["id"],
                    "paired_content": other_item.get("content", ""),
                    "paired_label": other_item.get("label"),
                    "self_label": self_item.get("label"),
                }
                conflicts[self_item["id"]] = detail

    return conflicts


# ── Pipeline 步骤：check ───────────────────────────────────────────────────────


async def run_conflict_detection(dataset_id: int) -> dict[str, Any]:
    db  = get_db()
    cfg = db.get_dataset_config(dataset_id)

    # 获取有标注的数据（enrich=True 以携带 annotations 列表和 label 字段）
    annotated_items = db.list_data_by_status(dataset_id, "annotated", enrich=True)
    if not annotated_items:
        return {"label_conflicts": 0, "semantic_conflicts": 0, "clean": 0, "total": 0}

    label_conflict_map    = detect_label_conflicts(annotated_items)
    semantic_conflict_map = detect_semantic_conflicts(annotated_items, cfg)

    clean_count = 0
    for item in annotated_items:
        data_id = item["id"]
        # 清除旧冲突记录（本次重跑覆盖）
        db.clear_conflicts(data_id)

        if data_id in label_conflict_map:
            db.create_conflict(data_id, "label_conflict", label_conflict_map[data_id],
                               created_by="pipeline")
            db.update_stage(data_id, "annotated")  # 保持 annotated，待人工处理
        elif data_id in semantic_conflict_map:
            db.create_conflict(data_id, "semantic_conflict", semantic_conflict_map[data_id],
                               created_by="pipeline")
            db.update_stage(data_id, "annotated")
        else:
            db.update_stage(data_id, "checked")
            clean_count += 1

    return {
        "label_conflicts": len(label_conflict_map),
        "semantic_conflicts": len(semantic_conflict_map),
        "clean": clean_count,
        "total": len(annotated_items),
    }


def get_conflict_items(dataset_id: int) -> list[dict[str, Any]]:
    db = get_db()
    return db.list_conflicts_by_dataset(dataset_id, status="open")
