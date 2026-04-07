# 数据模型 & NAS 存储结构

---

## 数据条目（Item）结构

每条数据存为一个 JSON 文件 `{id}.json`，完整字段：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "text": "我想了解一下寿险产品",
  "label": "寿险意图",
  "status": "labeled",
  "model_pred": "寿险意图",
  "model_score": 0.9243,
  "annotator": "admin",
  "annotated_at": "2025-01-15T09:32:11.123456",
  "conflict_flag": false,
  "conflict_type": null,
  "conflict_detail": null,
  "source_file": "upload_20250115.xlsx",
  "created_at": "2025-01-15T09:00:00.000000",
  "updated_at": "2025-01-15T09:32:11.123456"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 全局唯一标识 |
| `text` | string | 用户原始输入文本 |
| `label` | string \| null | 人工标注结果 |
| `status` | enum | 当前阶段（见状态机） |
| `model_pred` | string \| null | LLM 预测标签 |
| `model_score` | float \| null | 预测置信度 0-1 |
| `annotator` | string \| null | 标注员用户名 |
| `annotated_at` | ISO datetime \| null | 标注时间 |
| `conflict_flag` | bool | 是否有冲突 |
| `conflict_type` | "label_conflict" \| "semantic_conflict" \| null | 冲突类型 |
| `conflict_detail` | object \| null | 冲突详情（见下方） |
| `source_file` | string | 来源文件名 |
| `created_at` | ISO datetime | 上传时间 |
| `updated_at` | ISO datetime | 最后更新时间 |

### conflict_detail 结构

**标注冲突（label_conflict）**：
```json
{
  "text": "原始文本",
  "conflicting_labels": ["寿险意图", "拒识"],
  "annotators": [
    {"annotator": "user1", "label": "寿险意图"},
    {"annotator": "user2", "label": "拒识"}
  ]
}
```

**语义冲突（semantic_conflict）**：
```json
{
  "similarity": 0.9341,
  "threshold": 0.9,
  "paired_id": "另一条数据的 UUID",
  "paired_text": "另一条相似文本",
  "paired_label": "拒识",
  "self_label": "寿险意图"
}
```

---

## NAS 目录结构

```
nas/                          ← config.yaml → storage.base_path
├── raw/                      ← 原始上传数据
│   └── {id}.json
├── processed/                ← 清洗后
│   └── {id}.json
├── pre_annotated/            ← LLM 预标注后
│   └── {id}.json
├── labeling/                 ← 标注员"取走"、标注中
│   └── {id}.json
├── labeled/                  ← 人工标注完成（含冲突条目）
│   └── {id}.json
├── checked/                  ← 通过冲突检测，高质量数据
│   └── {id}.json
│
├── embeddings/               ← 向量文件（numpy .npy 格式）
│   └── {id}.npy              ← shape (dim,)，float32，已 L2 归一化
│
├── vector_index/             ← FAISS 索引文件
│   ├── faiss.index           ← FAISS IndexFlatIP 文件
│   └── ids.json              ← 与索引对应的 id 列表（顺序严格对应）
│
├── export/                   ← 导出文件
│   ├── datapluse_export_20250115_093045.json
│   └── datapluse_export_20250115_094512.xlsx
│
└── pipeline_status.json      ← Pipeline 当前状态
```

### pipeline_status.json 结构

```json
{
  "status": "completed",
  "current_step": "check",
  "progress": 100,
  "started_at": "2025-01-15T09:00:00",
  "finished_at": "2025-01-15T09:05:32",
  "updated_at": "2025-01-15T09:05:32",
  "error": null,
  "results": [
    {"step": "process",       "processed": 500},
    {"step": "pre_annotate",  "annotated": 500},
    {"step": "embed",         "embedded": 500, "index_size": 500},
    {"step": "check",         "label_conflicts": 3, "semantic_conflicts": 12, "clean": 485, "total": 500}
  ]
}
```

---

## NASManager 核心接口

`backend/storage/nas.py` 的 `NASManager` 类：

```python
# CRUD
nas.create(text, source_file)       → dict  # 写入 raw/
nas.get(item_id)                    → dict | None
nas.update(item)                    → dict  # 自动移动到正确目录
nas.delete(item_id)                 → bool

# 查询
nas.list_all(status, page, page_size) → {"total": N, "items": [...]}
nas.list_by_status(status)            → list[dict]  # 不分页
nas.stats()                           → {"total": N, "raw": N, ...}

# Embedding I/O
nas.save_embedding(item_id, vec)    # 写 embeddings/{id}.npy
nas.load_embedding(item_id)         → ndarray | None
nas.load_all_embeddings()           → dict[id, ndarray]

# 状态文件
nas.get_pipeline_status()           → dict
nas.set_pipeline_status(data)       # 写 pipeline_status.json

# 导出目录
nas.export_dir()                    → Path
nas.list_exports()                  → list[{"filename", "size", "created_at"}]
```

---

## 导出数据格式

导出字段（脱敏内部字段后）：

```
id | text | label | status | model_pred | model_score | annotator | annotated_at | source_file | created_at
```

JSON 格式为 `list[object]`，Excel 格式为单 Sheet 表格。
