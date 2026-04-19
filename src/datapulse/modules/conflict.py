"""
冲突检测模块（核心）

两种冲突类型：
1. 标注冲突（label_conflict）：同一数据被不同标注员赋予不同标签
2. 语义冲突（semantic_conflict）：语义相似度 > threshold 且 final_label 不同

结果写入 t_conflict 表。
干净数据 stage → checked；有冲突数据保持 annotated，等待人工裁决。

语义冲突设计要点：
- 参照池 = annotated（候选）+ checked（已通过历史数据）
  checked 数据也参与 FAISS 近邻查找，确保历史数据与新数据的跨阶段对比。
- min_annotation_count 仅用于 label_conflict 过滤，语义冲突只需有最终 label 即可。
- 若 checked 数据被新 annotated 数据"撞上"语义冲突，重新推回 annotated 等待裁决。
"""

from __future__ import annotations

import logging
from typing import Any

from datapulse.modules.vector import get_index
from datapulse.repository.base import get_db
from datapulse.repository.embeddings import get_emb

logger = logging.getLogger("datapulse.conflict")


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
    annotated_items: list[dict[str, Any]],
    checked_items: list[dict[str, Any]],
    dataset_id: int,
    cfg: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """
    语义相似度 > threshold 且 final_label 不同 → semantic_conflict

    参数：
      annotated_items — 待检测的候选数据（annotated 阶段，有最终 label）
      checked_items   — 历史参照数据（checked 阶段，有最终 label）

    流程：
      1. 参照池 = annotated + checked（全部有 label 的数据），构建 id_to_item 映射
      2. 对每条 annotated 候选，从磁盘加载预计算向量，向 FAISS 查 topk 近邻
      3. 近邻可以来自 annotated 或 checked——两者都在参照池中
      4. 近邻 label 与当前不同 → 语义冲突，双向写入 conflicts dict
      5. 向量不存在（未向量化）的条目静默跳过

    返回 {data_id: conflict_detail}，包含候选侧（annotated）和被匹配侧（checked）的条目。
    调用方根据条目原始 stage 决定如何处理（annotated 保持冲突，checked 重新开启）。
    """
    sim_cfg   = cfg.get("similarity", {})
    threshold = float(sim_cfg.get("threshold_high", 0.9))
    topk      = int(sim_cfg.get("topk", 5))

    # 候选：有最终 label 的 annotated 数据
    labeled_annotated = [i for i in annotated_items if i.get("label") is not None]
    if not labeled_annotated:
        return {}

    index = get_index(dataset_id)
    if index.size == 0:
        logger.warning("dataset=%d FAISS 索引为空，请先运行 embed 步骤或重建索引", dataset_id)
        return {}

    emb = get_emb()

    # ── 参照池：annotated + checked 的全部有 label 数据 ──────────────────────
    # checked 先入 map，annotated 后入（有重叠时 annotated 优先）
    labeled_checked = [i for i in checked_items if i.get("label") is not None]
    id_to_item: dict[int, dict[str, Any]] = {}
    for item in labeled_checked:
        id_to_item[int(item["id"])] = item
    for item in labeled_annotated:
        id_to_item[int(item["id"])] = item

    logger.info(
        "dataset=%d 语义冲突检测：候选 %d 条，参照池 %d 条（含 checked %d 条），"
        "threshold=%.2f，topk=%d",
        dataset_id,
        len(labeled_annotated),
        len(id_to_item),
        len(labeled_checked),
        threshold,
        topk,
    )

    conflict_pairs: set[tuple[int, int]] = set()
    conflicts: dict[int, dict[str, Any]] = {}

    for item in labeled_annotated:
        item_id    = int(item["id"])
        item_label = item["label"]

        # 从磁盘加载预计算向量（embed 步骤已写入），向量不存在则跳过
        vec = emb.load(dataset_id, item_id)
        if vec is None:
            logger.debug("dataset=%d item=%d 无预计算向量，跳过", dataset_id, item_id)
            continue

        # FAISS search，返回 [(data_id: int, similarity: float), ...]
        neighbors = index.search(vec, topk=topk + 1)

        for neighbor_id, sim in neighbors:
            # 排除自身 & 低于阈值
            if neighbor_id == item_id or sim < threshold:
                continue

            # 参照池包含 annotated + checked，checked 邻居现在可以被找到
            neighbor = id_to_item.get(neighbor_id)
            if neighbor is None:
                # 向量索引有该 ID 但参照池没有（向量索引比 DB 新/旧，正常现象），跳过
                continue
            if neighbor.get("label") == item_label:
                # 标签相同，不冲突
                continue

            # 去重：同一对只记录一次（但双向都写入 conflict）
            pair = (min(item_id, neighbor_id), max(item_id, neighbor_id))
            if pair in conflict_pairs:
                continue
            conflict_pairs.add(pair)

            logger.info(
                "dataset=%d 语义冲突：item=%d(%s) ↔ item=%d(%s) sim=%.4f",
                dataset_id,
                item_id, item_label,
                neighbor_id, neighbor.get("label"),
                sim,
            )

            # 双向记录，两条数据都标记为语义冲突
            for self_item, other_item in [(item, neighbor), (neighbor, item)]:
                conflicts[self_item["id"]] = {
                    "similarity":     round(sim, 4),
                    "threshold":      threshold,
                    "paired_id":      other_item["id"],
                    "paired_content": other_item.get("content", ""),
                    "paired_label":   other_item.get("label"),
                    "self_label":     self_item.get("label"),
                }

    return conflicts


# ── Pipeline 步骤：check ───────────────────────────────────────────────────────


async def run_conflict_detection(dataset_id: int) -> dict[str, Any]:
    db  = get_db()
    cfg = db.get_dataset_config(dataset_id)

    # ── 获取候选数据（annotated 待审查）和参照数据（checked 已通过）──────────────
    annotated_items = db.list_data_by_status(dataset_id, "annotated", enrich=True)
    checked_items   = db.list_data_by_status(dataset_id, "checked",   enrich=True)

    if not annotated_items:
        return {"label_conflicts": 0, "semantic_conflicts": 0, "clean": 0, "total": 0}

    # ── label_conflict：需满足 min_annotation_count（需要多人标注才能判断分歧）──
    min_count = cfg.get("pipeline", {}).get("min_annotation_count", 1)
    eligible_ids: set[int] = {
        item["id"]
        for item in annotated_items
        if len(item.get("annotations", [])) >= min_count
    }
    eligible_items = [item for item in annotated_items if item["id"] in eligible_ids]
    skipped_count  = len(annotated_items) - len(eligible_items)

    # ── semantic_conflict：只需有最终 label，不要求 min_annotation_count 个标注员 ──
    semantic_candidates = [item for item in annotated_items if item.get("label") is not None]

    label_conflict_map    = detect_label_conflicts(eligible_items)
    semantic_conflict_map = detect_semantic_conflicts(
        semantic_candidates, checked_items, dataset_id, cfg
    )

    logger.info(
        "dataset=%d 冲突检测：annotated=%d，checked=%d，"
        "label_conflicts=%d，semantic_conflict_entries=%d",
        dataset_id,
        len(annotated_items),
        len(checked_items),
        len(label_conflict_map),
        len(semantic_conflict_map),
    )

    # ── 处理 annotated 数据 ──────────────────────────────────────────────────────
    clean_count = 0
    for item in annotated_items:
        data_id = item["id"]
        db.clear_conflicts(data_id)

        if data_id in label_conflict_map:
            db.create_conflict(
                data_id, "label_conflict",
                label_conflict_map[data_id],
                created_by="pipeline",
            )
            db.update_stage(data_id, "annotated")
        elif data_id in semantic_conflict_map:
            db.create_conflict(
                data_id, "semantic_conflict",
                semantic_conflict_map[data_id],
                created_by="pipeline",
            )
            db.update_stage(data_id, "annotated")
        elif data_id in eligible_ids:
            # 满足 min_count 且无冲突 → 推进到 checked
            db.update_stage(data_id, "checked")
            clean_count += 1
        # else: 未达到 min_count，保持 annotated，等待更多标注员参与

    # ── 重新开启 checked 数据（与新 annotated 产生语义冲突）─────────────────────
    # 历史数据虽已通过审查，但新标注数据与其语义相近且标签不同，需重新裁决
    reopened_count = 0
    for item in checked_items:
        data_id = item["id"]
        if data_id in semantic_conflict_map:
            db.clear_conflicts(data_id)
            db.create_conflict(
                data_id, "semantic_conflict",
                semantic_conflict_map[data_id],
                created_by="pipeline",
            )
            db.update_stage(data_id, "annotated")
            reopened_count += 1
            logger.info(
                "dataset=%d checked→annotated（语义冲突重开）：item=%d label=%s",
                dataset_id, data_id, item.get("label"),
            )

    # 统计 annotated 侧的语义冲突数（不含 checked 侧被重开的）
    annotated_id_set = {item["id"] for item in annotated_items}
    annotated_semantic_count = sum(
        1 for data_id in semantic_conflict_map if data_id in annotated_id_set
    )

    return {
        "label_conflicts":    len(label_conflict_map),
        "semantic_conflicts": annotated_semantic_count,
        "clean":              clean_count,
        "reopened":           reopened_count,
        "total":              len(annotated_items),
        "skipped_low_count":  skipped_count,
    }


def get_conflict_items(dataset_id: int) -> list[dict[str, Any]]:
    db = get_db()
    return db.list_conflicts_by_dataset(dataset_id, status="open")
