"""
NAS 文件系统存储层
所有数据均以 JSON 文件形式存储，禁止使用数据库

目录结构：
  nas/
  ├── raw/           原始上传数据
  ├── processed/     清洗后
  ├── pre_annotated/ 预标注后
  ├── labeling/      标注中
  ├── labeled/       已标注
  ├── checked/       冲突检测通过
  ├── embeddings/    向量文件 (.npy)
  ├── vector_index/  FAISS 索引
  ├── export/        导出文件
  └── _manifest.json 内存索引快照（加速查询）

性能策略：
  - _manifest.json 保存所有条目的摘要字段，启动时一次性加载到内存 _index
  - 查询（list_all / stats）直接读内存，O(1)，无磁盘 I/O
  - 写操作（create / update / delete）同步更新内存后写 manifest
  - Pipeline 批量写时用 begin_bulk() / end_bulk()，批量结束后统一 flush
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np

from config.settings import get_settings

# 所有合法状态
STATUS_DIRS = [
    "raw",
    "processed",
    "pre_annotated",
    "labeling",
    "labeled",
    "checked",
]

PIPELINE_STATUS_FILE = "pipeline_status.json"

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# manifest 中保存的摘要字段（不含 text 全文以外的大字段）
SUMMARY_FIELDS = [
    "id",
    "text",
    "status",
    "label",
    "model_pred",
    "model_score",
    "conflict_flag",
    "conflict_type",
    "conflict_detail",
    "annotator",
    "annotated_at",
    "source_file",
    "created_at",
    "updated_at",
]


def _now() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


class NASManager:
    """NAS 文件系统操作单例，内置内存索引加速大规模查询"""

    def __init__(self) -> None:
        # id → summary dict（仅包含 SUMMARY_FIELDS）
        self._index: dict[str, dict] = {}
        self._bulk_mode = False
        self._ensure_dirs()
        self._load_manifest()

    # ── 路径辅助 ────────────────────────────────────────────────────────────

    def _base(self) -> Path:
        p = get_settings().storage_base_path
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _ensure_dirs(self) -> None:
        base = self._base()
        for d in STATUS_DIRS + ["embeddings", "vector_index", "export"]:
            (base / d).mkdir(parents=True, exist_ok=True)

    def dir(self, status: str) -> Path:
        return self._base() / status

    # ── Manifest 索引 ────────────────────────────────────────────────────────

    def _manifest_path(self) -> Path:
        return self._base() / "_manifest.json"

    def _load_manifest(self) -> None:
        """启动时加载 manifest 到内存；若不存在则从文件重建"""
        p = self._manifest_path()
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    self._index = json.load(f)
                return
            except Exception:
                pass
        # manifest 损坏或不存在 → 全量扫描重建
        self._rebuild_from_files()

    def _save_manifest(self) -> None:
        """原子写入 manifest（tmp → rename）"""
        p = self._manifest_path()
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False)
        tmp.rename(p)

    def _rebuild_from_files(self) -> None:
        """首次初始化或 manifest 损坏时，全量扫描所有 JSON 文件重建索引"""
        self._index = {}
        for status in STATUS_DIRS:
            for path in self.dir(status).glob("*.json"):
                try:
                    item = self._read(path)
                    self._index[item["id"]] = {
                        k: item.get(k) for k in SUMMARY_FIELDS
                    }
                except Exception:
                    pass
        self._save_manifest()

    def _update_index(self, item: dict[str, Any]) -> None:
        """更新内存索引并按需 flush"""
        self._index[item["id"]] = {k: item.get(k) for k in SUMMARY_FIELDS}
        if not self._bulk_mode:
            self._save_manifest()

    def begin_bulk(self) -> None:
        """开始批量写模式：暂缓 manifest flush，提升吞吐"""
        self._bulk_mode = True

    def end_bulk(self) -> None:
        """结束批量写模式，立即 flush manifest"""
        self._bulk_mode = False
        self._save_manifest()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(self, text: str, source_file: str = "") -> dict[str, Any]:
        """创建一条原始数据记录"""
        ts = _now()
        item: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "text": text,
            "label": None,
            "status": "raw",
            "model_pred": None,
            "model_score": None,
            "annotator": None,
            "annotated_at": None,
            "conflict_flag": False,
            "conflict_type": None,
            "conflict_detail": None,
            "source_file": source_file,
            "created_at": ts,
            "updated_at": ts,
        }
        self._write(item)
        self._update_index(item)
        return item

    def get(self, item_id: str) -> Optional[dict[str, Any]]:
        """按 ID 查找（先查内存索引定位 status，再读文件获取完整数据）"""
        summary = self._index.get(item_id)
        if summary is None:
            return None
        status = summary.get("status")
        if status:
            path = self.dir(status) / f"{item_id}.json"
            if path.exists():
                return self._read(path)
        # fallback：遍历所有目录（manifest 与实际文件不一致时）
        for s in STATUS_DIRS:
            path = self.dir(s) / f"{item_id}.json"
            if path.exists():
                return self._read(path)
        return None

    def update(self, item: dict[str, Any]) -> dict[str, Any]:
        """更新记录（如果状态变了，移动文件目录）"""
        item["updated_at"] = _now()
        # 先清除旧文件（借助索引快速定位旧 status）
        old_summary = self._index.get(item["id"])
        if old_summary:
            old_status = old_summary.get("status")
            if old_status:
                old_path = self.dir(old_status) / f"{item['id']}.json"
                if old_path.exists():
                    old_path.unlink()
            else:
                # fallback 遍历
                for s in STATUS_DIRS:
                    old = self.dir(s) / f"{item['id']}.json"
                    if old.exists():
                        old.unlink()
                        break
        else:
            for s in STATUS_DIRS:
                old = self.dir(s) / f"{item['id']}.json"
                if old.exists():
                    old.unlink()
                    break
        self._write(item)
        self._update_index(item)
        return item

    def delete(self, item_id: str) -> bool:
        summary = self._index.get(item_id)
        deleted = False
        # 优先用索引定位
        if summary and summary.get("status"):
            path = self.dir(summary["status"]) / f"{item_id}.json"
            if path.exists():
                path.unlink()
                deleted = True
        if not deleted:
            for status in STATUS_DIRS:
                path = self.dir(status) / f"{item_id}.json"
                if path.exists():
                    path.unlink()
                    deleted = True
                    break
        if deleted:
            # 同时删除 embedding
            emb_path = self.dir("embeddings") / f"{item_id}.npy"
            if emb_path.exists():
                emb_path.unlink()
            self._index.pop(item_id, None)
            if not self._bulk_mode:
                self._save_manifest()
        return deleted

    def list_all(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """分页查询，直接读内存索引，O(N) 过滤而非 O(N) 磁盘 I/O"""
        items = list(self._index.values())
        if status:
            items = [i for i in items if i.get("status") == status]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items[start: start + page_size],
        }

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        """返回某状态下全部记录完整数据（需要读文件，pipeline 用）"""
        items = []
        for path in self.dir(status).glob("*.json"):
            try:
                items.append(self._read(path))
            except Exception:
                pass
        return items

    def stats(self) -> dict[str, int]:
        """统计各状态数量，直接读内存，O(N) 单次遍历"""
        result: dict[str, int] = {s: 0 for s in STATUS_DIRS}
        result["total"] = 0
        for item in self._index.values():
            s = item.get("status")
            if s in result:
                result[s] += 1
                result["total"] += 1
        return result

    # ── Embedding I/O ─────────────────────────────────────────────────────────

    def save_embedding(self, item_id: str, vector: np.ndarray) -> None:
        path = self.dir("embeddings") / f"{item_id}.npy"
        np.save(str(path), vector)

    def load_embedding(self, item_id: str) -> Optional[np.ndarray]:
        path = self.dir("embeddings") / f"{item_id}.npy"
        if path.exists():
            return np.load(str(path))
        return None

    def load_all_embeddings(self) -> dict[str, np.ndarray]:
        result = {}
        for p in self.dir("embeddings").glob("*.npy"):
            result[p.stem] = np.load(str(p))
        return result

    # ── Vector index paths ────────────────────────────────────────────────────

    def vector_index_path(self) -> Path:
        return self.dir("vector_index") / "faiss.index"

    def vector_ids_path(self) -> Path:
        return self.dir("vector_index") / "ids.json"

    # ── Export ────────────────────────────────────────────────────────────────

    def export_dir(self) -> Path:
        return self.dir("export")

    def list_exports(self) -> list[dict[str, Any]]:
        exports = []
        for p in self.export_dir().iterdir():
            if p.is_file():
                exports.append({
                    "filename": p.name,
                    "size": p.stat().st_size,
                    "created_at": datetime.fromtimestamp(
                        p.stat().st_mtime, tz=SHANGHAI_TZ
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                })
        exports.sort(key=lambda x: x["created_at"], reverse=True)
        return exports

    # ── Pipeline status ───────────────────────────────────────────────────────

    def get_pipeline_status(self) -> dict[str, Any]:
        path = self._base() / PIPELINE_STATUS_FILE
        if path.exists():
            return self._read(path)
        return {"status": "idle", "current_step": None, "progress": 0, "detail": {}}

    def set_pipeline_status(self, data: dict[str, Any]) -> None:
        path = self._base() / PIPELINE_STATUS_FILE
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _write(self, item: dict[str, Any]) -> None:
        path = self.dir(item["status"]) / f"{item['id']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            return json.load(f)


_nas: NASManager | None = None


def get_nas() -> NASManager:
    global _nas
    if _nas is None:
        _nas = NASManager()
    return _nas
