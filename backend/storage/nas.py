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
  └── export/        导出文件
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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


class NASManager:
    """NAS 文件系统操作单例"""

    def __init__(self) -> None:
        self._ensure_dirs()

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

    # ── CRUD ───────────────────────────────────────────────────────────────

    def create(self, text: str, source_file: str = "") -> dict[str, Any]:
        """创建一条原始数据记录"""
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
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._write(item)
        return item

    def get(self, item_id: str) -> Optional[dict[str, Any]]:
        """按 ID 查找（遍历所有状态目录）"""
        for status in STATUS_DIRS:
            path = self.dir(status) / f"{item_id}.json"
            if path.exists():
                return self._read(path)
        return None

    def update(self, item: dict[str, Any]) -> dict[str, Any]:
        """更新记录（如果状态变了，移动文件目录）"""
        item["updated_at"] = datetime.utcnow().isoformat()
        # 先清除旧文件
        for status in STATUS_DIRS:
            old = self.dir(status) / f"{item['id']}.json"
            if old.exists():
                old.unlink()
        self._write(item)
        return item

    def delete(self, item_id: str) -> bool:
        for status in STATUS_DIRS:
            path = self.dir(status) / f"{item_id}.json"
            if path.exists():
                path.unlink()
                # 同时删除 embedding
                emb_path = self.dir("embeddings") / f"{item_id}.npy"
                if emb_path.exists():
                    emb_path.unlink()
                return True
        return False

    def list_all(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """分页查询，可按 status 过滤"""
        statuses = [status] if status else STATUS_DIRS
        items: list[dict[str, Any]] = []
        for s in statuses:
            for p in self.dir(s).glob("*.json"):
                try:
                    items.append(self._read(p))
                except Exception:
                    pass
        # 按创建时间倒序
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items[start : start + page_size],
        }

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        """返回某状态下全部记录（不分页）"""
        items = []
        for p in self.dir(status).glob("*.json"):
            try:
                items.append(self._read(p))
            except Exception:
                pass
        return items

    def stats(self) -> dict[str, int]:
        result: dict[str, int] = {"total": 0}
        for s in STATUS_DIRS:
            cnt = len(list(self.dir(s).glob("*.json")))
            result[s] = cnt
            result["total"] += cnt
        return result

    # ── Embedding I/O ──────────────────────────────────────────────────────

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

    # ── Vector index paths ─────────────────────────────────────────────────

    def vector_index_path(self) -> Path:
        return self.dir("vector_index") / "faiss.index"

    def vector_ids_path(self) -> Path:
        return self.dir("vector_index") / "ids.json"

    # ── Export ─────────────────────────────────────────────────────────────

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
                        p.stat().st_mtime
                    ).isoformat(),
                })
        exports.sort(key=lambda x: x["created_at"], reverse=True)
        return exports

    # ── Pipeline status ────────────────────────────────────────────────────

    def get_pipeline_status(self) -> dict[str, Any]:
        path = self._base() / PIPELINE_STATUS_FILE
        if path.exists():
            return self._read(path)
        return {"status": "idle", "current_step": None, "progress": 0}

    def set_pipeline_status(self, data: dict[str, Any]) -> None:
        path = self._base() / PIPELINE_STATUS_FILE
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Internals ──────────────────────────────────────────────────────────

    def _write(self, item: dict[str, Any]) -> None:
        path = self.dir(item["status"]) / f"{item['id']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


_nas: NASManager | None = None


def get_nas() -> NASManager:
    global _nas
    if _nas is None:
        _nas = NASManager()
    return _nas
