"""
冲突检测模块（核心）

两种冲突类型：
1. 标注冲突（label_conflict）：同一数据被不同标注员赋予不同标签
2. 语义冲突（semantic_conflict）：语义相似度 > threshold 且 final_label 不同

结果写入 t_conflict 表。
干净数据 stage → checked；有冲突数据保持 annotated，等待人工裁决。

语义冲突设计要点：
- 参照池 = annotated（候选）+ checked（已通过历史数据）
  checked 数据参与 FAISS 近邻查找，为 annotated 数据提供比对基准。
- min_annotation_count 仅用于 label_conflict 过滤，语义冲突只需有最终 label 即可。
- checked 数据永远不会被回退到 annotated，只有 annotated 侧写冲突记录。
  背景：若一条新 annotated 数据与 100 条 checked 数据语义冲突，
  不应将 100 条历史数据全部回退，只需标记该 annotated 数据等待人工裁决即可。
  如需在 checked 内部互检，请使用【高质量数据自检】功能（run_quality_self_check）。
"""

from __future__ import annotations

from typing import Any, Callable

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


# ── 语义冲突内部辅助函数 ────────────────────────────────────────────────────────


def _find_conflicting_neighbor(
    item_id: int,
    item_label: str,
    neighbor_id: int,
    sim: float,
    threshold: float,
    id_to_item: dict[int, dict[str, Any]],
    conflict_pairs: set[tuple[int, int]],
) -> tuple[tuple[int, int], dict[str, Any]] | None:
    """返回 (pair, neighbor)，若该邻居构成新的语义冲突；否则返回 None。"""
    if neighbor_id == item_id or sim < threshold:
        return None
    neighbor = id_to_item.get(neighbor_id)
    if neighbor is None or neighbor.get("label") == item_label:
        return None
    pair = (min(item_id, neighbor_id), max(item_id, neighbor_id))
    if pair in conflict_pairs:
        return None
    return pair, neighbor


def _process_semantic_candidate(
    item: dict[str, Any],
    vec_map: dict[int, Any],
    index: Any,
    topk: int,
    threshold: float,
    id_to_item: dict[int, dict[str, Any]],
    conflict_pairs: set[tuple[int, int]],
    conflicts: dict[int, dict[str, Any]],
    dataset_id: int,
) -> None:
    """处理单条候选数据，就地更新 conflict_pairs 和 conflicts。"""
    item_id    = int(item["id"])
    item_label = item["label"]
    vec = vec_map.get(item_id)
    if vec is None:
        _log.debug("no precomputed vector, skipping", dataset_id=dataset_id, item_id=item_id)
        return
    for neighbor_id, sim in index.search(vec, topk=topk + 1):
        result = _find_conflicting_neighbor(
            item_id, item_label, neighbor_id, sim, threshold, id_to_item, conflict_pairs
        )
        if result is None:
            continue
        pair, neighbor = result
        conflict_pairs.add(pair)
        _log.info(
            "semantic conflict found",
            dataset_id=dataset_id,
            item_a=item_id, label_a=item_label,
            item_b=neighbor_id, label_b=neighbor.get("label"),
            similarity=round(sim, 4),
        )
        existing = conflicts.get(item_id)
        if existing is None or round(sim, 4) > existing.get("similarity", 0):
            conflicts[item_id] = {
                "similarity":     round(sim, 4),
                "threshold":      threshold,
                "paired_id":      neighbor_id,
                "paired_content": neighbor.get("content", ""),
                "paired_label":   neighbor.get("label"),
                "self_label":     item_label,
            }


def _process_self_check_candidate(
    item: dict[str, Any],
    vec_map: dict[int, Any],
    index: Any,
    topk: int,
    threshold: float,
    checked_id_to_item: dict[int, dict[str, Any]],
    conflict_pairs: set[tuple[int, int]],
    conflict_map: dict[int, dict[str, Any]],
    dataset_id: int,
) -> None:
    """处理单条自检数据，双向写入 conflict_map。"""
    item_id    = int(item["id"])
    item_label = item["label"]
    vec = vec_map.get(item_id)
    if vec is None:
        _log.debug("no precomputed vector, skipping in self-check", item_id=item_id)
        return
    for neighbor_id, sim in index.search(vec, topk=topk + 1):
        result = _find_conflicting_neighbor(
            item_id, item_label, neighbor_id, sim, threshold, checked_id_to_item, conflict_pairs
        )
        if result is None:
            continue
        pair, neighbor = result
        conflict_pairs.add(pair)
        _log.info(
            "self-check conflict found",
            dataset_id=dataset_id,
            item_a=item_id, label_a=item_label,
            item_b=neighbor_id, label_b=neighbor.get("label"),
            similarity=round(sim, 4),
        )
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
      2. 一次 DB 查询批量加载所有候选向量（消除 N 次逐条查询）
      3. 对每条 annotated 候选，向 FAISS 查 topk 近邻
      4. 近邻可以来自 annotated 或 checked——两者都在参照池中
      5. 近邻 label 与当前不同 → 语义冲突，仅在 annotated 侧写冲突记录
      6. 向量不存在（未向量化）的条目静默跳过

    返回 {data_id: conflict_detail}，仅包含 annotated 侧的条目。
    checked 侧永远不写入，保持 checked stage 不变（由调用方保证）。
    如需检测 checked 内部冲突，请使用 run_quality_self_check。
    """
    sim_cfg   = cfg.get("similarity", {})
    threshold = float(sim_cfg.get("threshold_high", 0.9))
    topk      = int(sim_cfg.get("topk", 3))

    # 候选：有最终 label 的 annotated 数据
    labeled_annotated = [i for i in annotated_items if i.get("label") is not None]
    if not labeled_annotated:
        return {}

    index = get_index(dataset_id)
    if index.size == 0:
        _log.warning("FAISS index is empty, run embed step first", dataset_id=dataset_id)
        return {}

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

    # 一次 DB 查询批量加载所有候选向量，消除 N 次逐条 DB 查询
    candidate_ids = [int(i["id"]) for i in labeled_annotated]
    vec_map       = get_emb().load_batch(dataset_id, candidate_ids)

    conflict_pairs: set[tuple[int, int]] = set()
    conflicts: dict[int, dict[str, Any]] = {}

    for item in labeled_annotated:
        _process_semantic_candidate(
            item, vec_map, index, topk, threshold,
            id_to_item, conflict_pairs, conflicts, dataset_id,
        )

    return conflicts


# ── Pipeline 步骤：check ───────────────────────────────────────────────────────


async def run_conflict_detection(
    dataset_id: int,
    operator: str = "pipeline",
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """冲突检测主流程。

    on_progress(pct, msg) 在各阶段完成后回调，供调用方更新进度条。

    性能设计：
      - enrich=False 加载原始数据（1 次 SELECT）
      - enrich_for_conflict 批量填充 annotations + label（2 次 IN 查询）
      - 写回阶段全部批量操作（batch_clear + batch_create + bulk_update_stage × 2）
      总 DB 查询数 = O(1)，不再随数据量线性增长。
    """
    def _progress(pct: int, msg: str = "") -> None:
        if on_progress:
            on_progress(pct, msg)

    db  = get_db()
    cfg = db.get_dataset_config(dataset_id)

    # ── Step 1: 加载原始数据（不 enrich，避免 N×4 查询）────────────────────────
    _progress(10, "加载数据")
    annotated_items = db.list_data_by_status(dataset_id, "annotated", enrich=False)
    checked_items   = db.list_data_by_status(dataset_id, "checked",   enrich=False)

    if not annotated_items:
        _progress(100, "无待检测数据")
        return {"label_conflicts": 0, "semantic_conflicts": 0, "clean": 0, "total": 0}

    # ── Step 2: 批量填充冲突检测所需字段（2+2 次 IN 查询，替代 N×4 全量 enrich）──
    _progress(20, "加载标注数据")
    db.enrich_for_conflict(annotated_items)
    db.enrich_for_conflict(checked_items)

    # ── Step 3: 标注冲突检测（纯内存，极快）────────────────────────────────────
    _progress(30, "检测标注冲突")
    min_count = cfg.get("pipeline", {}).get("min_annotation_count", 1)
    eligible_ids: set[int] = {
        item["id"]
        for item in annotated_items
        if len(item.get("annotations", [])) >= min_count
    }
    eligible_items = [item for item in annotated_items if item["id"] in eligible_ids]
    skipped_count  = len(annotated_items) - len(eligible_items)
    label_conflict_map = detect_label_conflicts(eligible_items)

    # ── Step 4: 语义冲突检测（FAISS，内存操作）──────────────────────────────────
    _progress(45, "语义相似度搜索")
    semantic_candidates = [item for item in annotated_items if item.get("label") is not None]
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

    # ── Step 5: 批量写回（共 4~5 次 DB 操作，替代 N×3 逐条写入）────────────────
    _progress(70, "写入冲突记录")

    # 一次 DELETE IN 清除全部旧冲突
    all_annotated_ids = [item["id"] for item in annotated_items]
    db.batch_clear_conflicts(all_annotated_ids)

    conflict_records:   list[dict[str, Any]] = []
    conflict_item_ids:  list[int]            = []
    clean_ids:          list[int]            = []

    for item in annotated_items:
        data_id = item["id"]
        if data_id in label_conflict_map:
            conflict_records.append({
                "data_id":       data_id,
                "conflict_type": "label_conflict",
                "detail":        label_conflict_map[data_id],
                "created_by":    operator,
            })
            conflict_item_ids.append(data_id)
        elif data_id in semantic_conflict_map:
            conflict_records.append({
                "data_id":       data_id,
                "conflict_type": "semantic_conflict",
                "detail":        semantic_conflict_map[data_id],
                "created_by":    operator,
            })
            conflict_item_ids.append(data_id)
        elif data_id in eligible_ids:
            clean_ids.append(data_id)
        # else: 未达到 min_count，保持 annotated，等待更多标注员参与

    # 批量写入（各 1~2 次 DB 操作）
    db.batch_create_conflicts(conflict_records)
    if conflict_item_ids:
        db.bulk_update_stage(conflict_item_ids, "annotated", updated_by=operator)
    if clean_ids:
        db.bulk_update_stage(clean_ids, "checked", updated_by=operator)

    _progress(95, "完成")

    return {
        "label_conflicts":    len(label_conflict_map),
        "semantic_conflicts": len(semantic_conflict_map),
        "clean":              len(clean_ids),
        "total":              len(annotated_items),
        "skipped_low_count":  skipped_count,
    }


def get_conflict_items(dataset_id: int) -> list[dict[str, Any]]:
    db = get_db()
    return db.list_conflicts_by_dataset(dataset_id, status="open")


# ── 高质量数据自检（checked 内部互检）─────────────────────────────────────────


async def run_quality_self_check(dataset_id: int, operator: str = "pipeline") -> dict[str, Any]:
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
    topk      = int(sim_cfg.get("topk", 3))

    # 加载所有 checked 且有 final_label 的数据（enrich=False + 批量填充，避免 N×4 查询）
    # 排除 label_source == 'manual' 的条目：这类数据已经过人工冲突裁决，
    # 裁决结果本身就是权威标签，不应再被纳入语义互检范围。
    checked_items = db.list_data_by_status(dataset_id, "checked", enrich=False)
    db.enrich_for_conflict(checked_items)   # 2 次 IN 查询批量填充 annotations + label
    labeled_checked = [
        i for i in checked_items
        if i.get("label") is not None and i.get("label_source") != "manual"
    ]

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

    # 构建 checked id → item 映射，仅用于过滤"近邻也是 checked"
    checked_id_to_item: dict[int, dict[str, Any]] = {
        int(i["id"]): i for i in labeled_checked
    }

    # 一次 DB 查询批量加载所有 checked 向量，消除 N 次逐条 DB 查询
    all_checked_ids = [int(i["id"]) for i in labeled_checked]
    vec_map         = get_emb().load_batch(dataset_id, all_checked_ids)

    conflict_pairs: set[tuple[int, int]] = set()  # 去重
    conflict_map:   dict[int, dict[str, Any]] = {}  # data_id → conflict_detail

    for item in labeled_checked:
        _process_self_check_candidate(
            item, vec_map, index, topk, threshold,
            checked_id_to_item, conflict_pairs, conflict_map, dataset_id,
        )

    conflicts_found = len(conflict_pairs)
    items_reopened  = len(conflict_map)

    _log.info(
        "quality self-check completed",
        dataset_id=dataset_id,
        total_checked=total_checked,
        conflict_pairs=conflicts_found,
        items_reopened=items_reopened,
    )

    # 写入冲突记录，将涉及数据推回 annotated（批量操作，3 次 DB 代替 3N 次）
    conflict_data_ids = list(conflict_map.keys())
    db.batch_clear_conflicts(conflict_data_ids)
    db.batch_create_conflicts([
        {
            "data_id":       data_id,
            "conflict_type": "semantic_conflict",
            "detail":        detail,
            "created_by":    operator,
        }
        for data_id, detail in conflict_map.items()
    ])
    if conflict_data_ids:
        db.bulk_update_stage(conflict_data_ids, "annotated", updated_by=operator)

    return {
        "total_checked":  total_checked,
        "conflicts_found": conflicts_found,
        "items_reopened":  items_reopened,
    }
