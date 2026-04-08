"""
冲突检测模块（核心）

两种冲突类型：
1. 标注冲突（label_conflict）：同一文本被不同标注员赋予不同标签
2. 语义冲突（semantic_conflict）：语义高度相似（cosine > threshold）但标签不同

所有操作均按 dataset_id 隔离，相似度阈值从 dataset 配置读取。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from datapulse.modules.embedding import embed_text
from datapulse.modules.vector import get_index
from datapulse.repository.base import get_db
from datapulse.repository.embeddings import get_emb

# ── 标注冲突检测 ───────────────────────────────────────────────────────────────


def detect_label_conflicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if item.get("label") is not None:
            text_groups[item["text"]].append(item)

    conflicts = []
    for text, group in text_groups.items():
        labels = {i["label"] for i in group}
        if len(labels) > 1:
            for item in group:
                item = dict(item)
                item["conflict_flag"] = True
                item["conflict_type"] = "label_conflict"
                item["conflict_detail"] = {
                    "text": text,
                    "conflicting_labels": list(labels),
                    "annotators": [{"annotator": i.get("annotator"), "label": i["label"]} for i in group],
                }
                conflicts.append(item)
    return conflicts


# ── 语义冲突检测 ───────────────────────────────────────────────────────────────


def detect_semantic_conflicts(
    dataset_id: int,
    items: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    sim_cfg = cfg.get("similarity", {})
    threshold = sim_cfg.get("threshold_high", 0.9)
    topk = sim_cfg.get("topk", 5)

    labeled = [i for i in items if i.get("label") is not None]
    if len(labeled) < 2:
        return []

    db = get_db()
    emb = get_emb()
    index = get_index()

    conflict_ids: set[str] = set()
    conflicts: list[dict[str, Any]] = []

    for item in labeled:
        item_id = item["id"]
        item_label = item["label"]

        vec = emb.load(item_id)
        if vec is None:
            vec = embed_text(item["text"], cfg)
            emb.save(item_id, vec)

        if index.size == 0:
            continue

        neighbors = index.search(vec, topk=topk + 1)
        for neighbor_id, sim in neighbors:
            if neighbor_id == item_id or sim < threshold:
                continue
            neighbor = db.get_data(neighbor_id)
            if neighbor is None or neighbor.get("label") is None:
                continue
            if neighbor["label"] == item_label:
                continue

            pair_key = tuple(sorted([item_id, neighbor_id]))
            if pair_key in conflict_ids:
                continue
            conflict_ids.add(pair_key)

            for conflict_item, other_item in [(item, neighbor), (neighbor, item)]:
                c = dict(conflict_item)
                c["conflict_flag"] = True
                c["conflict_type"] = "semantic_conflict"
                c["conflict_detail"] = {
                    "similarity": round(sim, 4),
                    "threshold": threshold,
                    "paired_id": other_item["id"],
                    "paired_text": other_item["text"],
                    "paired_label": other_item["label"],
                    "self_label": conflict_item.get("label"),
                }
                conflicts.append(c)

    return conflicts


# ── Pipeline 步骤：check ───────────────────────────────────────────────────────


async def run_conflict_detection(dataset_id: int) -> dict[str, Any]:
    db = get_db()
    cfg = db.get_dataset_config(dataset_id)
    labeled_items = db.list_data_by_status(dataset_id, "labeled")
    if not labeled_items:
        return {"label_conflicts": 0, "semantic_conflicts": 0, "clean": 0, "total": 0}

    label_conflicts = detect_label_conflicts(labeled_items)
    label_conflict_ids = {i["id"] for i in label_conflicts}

    semantic_conflicts = detect_semantic_conflicts(dataset_id, labeled_items, cfg)
    semantic_conflict_ids = {i["id"] for i in semantic_conflicts}

    clean_count = 0
    for item in labeled_items:
        item = dict(item)
        if item["id"] in label_conflict_ids:
            item["conflict_flag"] = True
            item["conflict_type"] = "label_conflict"
            item["status"] = "labeled"
        elif item["id"] in semantic_conflict_ids:
            item["conflict_flag"] = True
            item["conflict_type"] = "semantic_conflict"
            item["status"] = "labeled"
        else:
            item["conflict_flag"] = False
            item["conflict_type"] = None
            item["conflict_detail"] = None
            item["status"] = "checked"
            clean_count += 1
        db.update_data(item)

    return {
        "label_conflicts": len(label_conflict_ids),
        "semantic_conflicts": len(semantic_conflict_ids),
        "clean": clean_count,
        "total": len(labeled_items),
    }


def get_conflict_items(dataset_id: int) -> list[dict[str, Any]]:
    db = get_db()
    items = db.list_data_by_status(dataset_id, "labeled")
    return [i for i in items if i.get("conflict_flag")]
