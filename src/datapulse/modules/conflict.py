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

from typing import Any

import structlog

from datapulse.modules.vector import get_index
from datapulse.repository.base import get_db
from datapulse.repository.embeddings import get_emb

_log = structlog.get_logger(__name__)


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
        _log.warning("FAISS index is empty, run embed step first", dataset_id=dataset_id)
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

    _log.info(
        "semantic conflict detection started",
        dataset_id=dataset_id,
        candidates=len(labeled_annotated),
        reference_pool=len(id_to_item),
        checked_in_pool=len(labeled_checked),
        threshold=threshold,
        topk=topk,
    )

    conflict_pairs: set[tuple[int, int]] = set()
    conflicts: dict[int, dict[str, Any]] = {}

    for item in labeled_annotated:
        item_id    = int(item["id"])
        item_label = item["label"]

        # 从磁盘加载预计算向量（embed 步骤已写入），向量不存在则跳过
        vec = emb.load(dataset_id, item_id)
        if vec is None:
            _log.debug("no precomputed vector, skipping", dataset_id=dataset_id, item_id=item_id)
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

            _log.info(
                "semantic conflict found",
                dataset_id=dataset_id,
                item_a=item_id, label_a=item_label,
                item_b=neighbor_id, label_b=neighbor.get("label"),
                similarity=round(sim, 4),
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

    _log.info(
        "conflict detection summary",
        dataset_id=dataset_id,
        annotated=len(annotated_items),
        checked=len(checked_items),
        label_conflicts=len(label_conflict_map),
        semantic_conflict_entries=len(semantic_conflict_map),
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
            _log.info(
                "checked item reopened due to semantic conflict",
                dataset_id=dataset_id, item_id=data_id, label=item.get("label"),
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


# ── 高质量数据自检（checked 内部互检）─────────────────────────────────────────


async def run_quality_self_check(dataset_id: int) -> dict[str, Any]:
    """
    高质量数据自检：在所有 checked 数据内部找语义相似但标签不同的冲突对。

    适用场景：
      批量初始化为 checked 的数据从未经过冲突检测，需在 checked 内部横向比对。

    算法设计（O(N × topk) FAISS 搜索，效率最优）：
      1. 加载 dataset 下全部 checked 且有最终 label 的数据
      2. 直接复用已有 FAISS 索引（embed 步骤已建好），无需重新构建
      3. 对每条 checked 数据，搜 topk 近邻
      4. 过滤条件：近邻也是 checked、标签不同、相似度 > threshold_high
      5. (min_id, max_id) 去重，保证每对只处理一次
      6. 命中的数据对：写入 semantic_conflict，stage → annotated，等待人工裁决

    返回 {"total_checked", "conflicts_found", "items_reopened"}
    """
    db  = get_db()
    cfg = db.get_dataset_config(dataset_id)

    sim_cfg   = cfg.get("similarity", {})
    threshold = float(sim_cfg.get("threshold_high", 0.9))
    topk      = int(sim_cfg.get("topk", 5))

    # 加载所有 checked 且有 final_label 的数据
    checked_items = db.list_data_by_status(dataset_id, "checked", enrich=True)
    labeled_checked = [i for i in checked_items if i.get("label") is not None]

    total_checked = len(labeled_checked)
    _log.info(
        "quality self-check started",
        dataset_id=dataset_id,
        total_checked=total_checked,
        threshold=threshold,
        topk=topk,
    )

    if total_checked == 0:
        return {"total_checked": 0, "conflicts_found": 0, "items_reopened": 0}

    index = get_index(dataset_id)
    if index.size == 0:
        _log.warning("FAISS index is empty, cannot run self-check", dataset_id=dataset_id)
        return {"total_checked": total_checked, "conflicts_found": 0, "items_reopened": 0}

    emb = get_emb()

    # 构建 checked id → item 映射，仅用于过滤"近邻也是 checked"
    checked_id_to_item: dict[int, dict[str, Any]] = {
        int(i["id"]): i for i in labeled_checked
    }

    conflict_pairs: set[tuple[int, int]] = set()  # 去重
    conflict_map:   dict[int, dict[str, Any]] = {}  # data_id → conflict_detail

    for item in labeled_checked:
        item_id    = int(item["id"])
        item_label = item["label"]

        vec = emb.load(dataset_id, item_id)
        if vec is None:
            _log.debug("no precomputed vector, skipping in self-check", item_id=item_id)
            continue

        neighbors = index.search(vec, topk=topk + 1)

        for neighbor_id, sim in neighbors:
            if neighbor_id == item_id or sim < threshold:
                continue

            # 近邻必须也是 checked
            neighbor = checked_id_to_item.get(neighbor_id)
            if neighbor is None:
                continue

            # 标签相同则不冲突
            if neighbor.get("label") == item_label:
                continue

            pair = (min(item_id, neighbor_id), max(item_id, neighbor_id))
            if pair in conflict_pairs:
                continue
            conflict_pairs.add(pair)

            _log.info(
                "self-check conflict found",
                dataset_id=dataset_id,
                item_a=item_id, label_a=item_label,
                item_b=neighbor_id, label_b=neighbor.get("label"),
                similarity=round(sim, 4),
            )

            # 双向写入 conflict_map
            for self_item, other_item in [(item, neighbor), (neighbor, item)]:
                conflict_map[int(self_item["id"])] = {
                    "similarity":     round(sim, 4),
                    "threshold":      threshold,
                    "paired_id":      int(other_item["id"]),
                    "paired_content": other_item.get("content", ""),
                    "paired_label":   other_item.get("label"),
                    "self_label":     self_item.get("label"),
                    "check_type":     "quality_self_check",
                }

    conflicts_found = len(conflict_pairs)
    items_reopened  = len(conflict_map)

    _log.info(
        "quality self-check completed",
        dataset_id=dataset_id,
        total_checked=total_checked,
        conflict_pairs=conflicts_found,
        items_reopened=items_reopened,
    )

    # 写入冲突记录，将涉及数据推回 annotated
    for data_id, detail in conflict_map.items():
        db.clear_conflicts(data_id)
        db.create_conflict(data_id, "semantic_conflict", detail, created_by="self_check")
        db.update_stage(data_id, "annotated")

    return {
        "total_checked":  total_checked,
        "conflicts_found": conflicts_found,
        "items_reopened":  items_reopened,
    }
