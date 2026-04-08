# 数据模型 & 数据库表结构

---

## 数据条目（DataItem）字段

每条数据存为 `data_items` 表的一行，完整字段：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "dataset_id": "default",
  "text": "我想了解一下寿险产品",
  "label": "寿险意图",
  "status": "labeled",
  "model_pred": "寿险意图",
  "model_score": 0.9243,
  "annotator": "admin",
  "annotated_at": "2025-01-15T09:32:11",
  "conflict_flag": false,
  "conflict_type": null,
  "conflict_detail": null,
  "source_file": "upload_20250115.xlsx",
  "created_at": "2025-01-15T09:00:00",
  "updated_at": "2025-01-15T09:32:11"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 全局唯一标识 |
| `dataset_id` | VARCHAR(36) FK | 所属 dataset |
| `text` | TEXT | 用户原始输入文本 |
| `label` | VARCHAR(100) null | 人工标注结果 |
| `status` | VARCHAR(32) | 当前阶段（见状态机） |
| `model_pred` | VARCHAR(100) null | LLM 预测标签 |
| `model_score` | FLOAT null | 预测置信度 0-1 |
| `annotator` | VARCHAR(100) null | 标注员用户名 |
| `annotated_at` | TIMESTAMP null | 标注时间 |
| `conflict_flag` | BOOLEAN | 是否有冲突 |
| `conflict_type` | VARCHAR(32) null | 冲突类型 |
| `conflict_detail` | JSONB null | 冲突详情 |
| `source_file` | VARCHAR(255) | 来源文件名 |
| `created_at` | TIMESTAMP | 上传时间 |
| `updated_at` | TIMESTAMP | 最后更新时间 |

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

## 数据库表结构（v0.5.0）

完整 DDL 见 `database/init.sql`（含字段 COMMENT）。

### datasets — 数据集（顶级隔离单元）

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(36) PK | 数据集 ID（slug 格式） |
| name | VARCHAR(100) | 显示名称 |
| description | TEXT | 描述 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

预置一条 `id='default'` 的默认数据集。

---

### system_config — 系统配置（per-dataset JSONB）

| 列 | 类型 | 说明 |
|----|------|------|
| dataset_id | VARCHAR(36) PK FK→datasets | 数据集 ID |
| config_data | JSONB | 完整配置（见下方结构） |
| updated_at | TIMESTAMP | 更新时间 |

**config_data 默认结构**：

```json
{
  "llm": {
    "use_mock": true,
    "api_url": "",
    "model_name": "",
    "timeout": 30
  },
  "embedding": {
    "use_mock": true,
    "model_path": "./models/bge-base-zh",
    "batch_size": 64
  },
  "similarity": {
    "threshold_high": 0.9,
    "threshold_mid": 0.8,
    "topk": 5
  },
  "pipeline": {
    "batch_size": 32
  },
  "labels": ["寿险意图", "拒识", "健康险意图", "财险意图", "其他意图"]
}
```

---

### roles — 角色表

| 列 | 类型 | 说明 |
|----|------|------|
| name | VARCHAR(50) PK | 角色名称 |
| description | TEXT | 描述 |
| permissions | JSONB | 权限列表，`["*"]` 表示全部 |

预置角色：
- `admin`：`["*"]`
- `annotator`：`["annotation:read","annotation:write","data:read"]`
- `viewer`：`["annotation:read","data:read"]`

---

### users — 用户表

| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | 用户 ID |
| username | VARCHAR(50) UNIQUE | 登录用户名 |
| password_hash | VARCHAR(255) | bcrypt 哈希 |
| display_name | VARCHAR(100) null | 显示名称 |
| is_active | BOOLEAN | 账号是否启用 |
| last_login | TIMESTAMP null | 最后登录时间 |
| created_at | TIMESTAMP | 创建时间 |

---

### user_roles — 用户-角色关联

| 列 | 类型 | 说明 |
|----|------|------|
| user_id | UUID FK→users | 用户 ID |
| role_name | VARCHAR(50) FK→roles | 角色名称 |

联合主键 (user_id, role_name)。

---

### pipeline_status — Pipeline 运行状态（per-dataset）

| 列 | 类型 | 说明 |
|----|------|------|
| dataset_id | VARCHAR(36) PK FK | 数据集 ID |
| status | VARCHAR(32) | running/completed/error/idle |
| current_step | VARCHAR(32) | process/pre_annotate/embed/check |
| progress | INTEGER | 0-100 |
| detail | JSONB | 进度详情（processed/total/speed/eta） |
| started_at | TIMESTAMP null | 开始时间 |
| finished_at | TIMESTAMP null | 结束时间 |
| updated_at | TIMESTAMP | 最后更新时间 |
| error | TEXT null | 错误信息 |
| results | JSONB null | 各步骤结果汇总 |

---

### export_templates — 导出模板（per-dataset）

| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | 模板 ID |
| dataset_id | VARCHAR(36) FK | 所属 dataset |
| name | VARCHAR(100) | 模板名称 |
| description | TEXT null | 描述 |
| format | VARCHAR(20) | json/excel/csv |
| columns | JSONB | 字段映射列表 |
| filters | JSONB | 过滤条件 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

---

## 向量文件结构（本地）

```
nas/                            ← config.yaml → storage.base_path
├── embeddings/
│   └── {item_id}.npy           ← shape (dim,)，float32，已 L2 归一化
└── vector_index/
    ├── faiss.index             ← FAISS IndexFlatIP 文件
    └── ids.json                ← 与索引对应的 item_id 列表（顺序严格对应）
```

---

## DBManager 核心接口

`backend/storage/db.py` 的 `DBManager`：

```python
# Dataset CRUD
db.list_datasets()                      → list[dict]
db.get_dataset(dataset_id)              → dict | None
db.create_dataset(id, name, ...)        → dict
db.update_dataset(id, ...)              → dict
db.delete_dataset(id)                   → bool

# Config（热更新，每次查 DB）
db.get_dataset_config(dataset_id)       → dict  # deep_merge(DEFAULT, db_row)
db.set_dataset_config(dataset_id, cfg)  → None

# Data CRUD（全部按 dataset_id 隔离）
db.create(dataset_id, text, source_file) → dict
db.get(item_id)                         → dict | None
db.update(item)                         → dict
db.delete(item_id)                      → bool
db.list_all(dataset_id, status, page, page_size) → {"total": N, "items": [...]}
db.list_by_status(dataset_id, status)   → list[dict]
db.stats(dataset_id)                    → {"total": N, "raw": N, ...}

# Pipeline 状态
db.get_pipeline_status(dataset_id)      → dict
db.set_pipeline_status(dataset_id, data) → None

# 模板
db.list_templates(dataset_id)           → list[dict]
db.get_template(template_id)            → dict | None
db.create_template(dataset_id, ...)     → dict
db.update_template(template_id, ...)    → dict
db.delete_template(template_id)         → bool

# 用户 & 角色（RBAC）
db.list_users()                         → list[dict]
db.get_user_by_username(username)       → dict | None  # 含 password_hash
db.create_user(username, password_hash, ...)  → dict
db.update_user(user_id, ...)            → dict
db.delete_user(user_id)                 → bool
db.list_roles()                         → list[dict]

# 初始化（startup 调用）
db.seed_defaults()                      # 写入预置角色 + 默认 dataset（幂等）
db.seed_admin_from_yaml(username, pw)   # 兼容迁移：首次创建 admin
```
