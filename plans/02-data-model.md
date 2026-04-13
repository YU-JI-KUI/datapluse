# 数据模型 & 数据库表结构（v2.0）

> **重构说明**：v2.0 将原单表 `data_items` 拆分为 6 张专职表，实现多人标注、版本追溯和全链路审计。

---

## 设计原则

- 表名以 `t_` 为前缀，字段使用 `snake_case`，关键字段附中文 COMMENT
- 主键统一为 `BIGSERIAL`（64-bit 自增整数）
- **无物理外键**，全部通过逻辑关联（`dataset_id`, `data_id`, `username`）
- 时间字段使用 `TIMESTAMP(6)`（微秒精度），统一存 UTC
- 用户关联基于 `username VARCHAR`，不用 `user_id`
- `t_data_item.status` 是 `t_data_state.stage` 的冗余缓存，供高频过滤使用

---

## 核心数据流

```
上传文件 → t_data_item(raw)
            ↓ pipeline process
         t_data_item(cleaned) + t_data_state(cleaned)
            ↓ LLM 预标注
         t_pre_annotation + t_data_item(pre_annotated)
            ↓ 人工标注
         t_annotation(is_active=true) + t_data_item(annotated)
            ↓ 冲突检测 / 质检
         t_conflict + t_data_item(checked)
```

---

## 表结构总览

### t_dataset — 数据集（顶级隔离单元）

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 数据集 ID |
| name | VARCHAR(100) | 显示名称 |
| description | TEXT | 描述 |
| status | VARCHAR(20) | active / inactive |
| created_by | VARCHAR(100) | 创建人 username |
| created_at | TIMESTAMP(6) | 创建时间 |
| updated_at | TIMESTAMP(6) | 更新时间 |

---

### t_system_config — 系统配置（per-dataset JSONB）

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 配置 ID |
| dataset_id | BIGINT | 逻辑 FK → t_dataset |
| config_data | JSONB | 完整配置（见下） |
| updated_at | TIMESTAMP(6) | 更新时间 |
| updated_by | VARCHAR(100) | 操作人 username |

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

### t_role — 角色表

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 角色 ID |
| name | VARCHAR(50) UNIQUE | 角色名（admin/annotator/viewer） |
| description | TEXT | 描述 |
| permissions | JSONB | 权限字符串数组，`["*"]` 表示全部 |
| created_at | TIMESTAMP(6) | 创建时间 |

预置角色：
- `admin`：`["*"]`
- `annotator`：`["annotation:read","annotation:write","data:read"]`
- `viewer`：`["annotation:read","data:read"]`

---

### t_user — 用户表

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 用户 ID |
| username | VARCHAR(100) UNIQUE | 登录用户名（全局唯一） |
| password_hash | VARCHAR(255) | bcrypt 哈希 |
| email | VARCHAR(200) | 邮箱（可空） |
| is_active | BOOLEAN | 账号启用状态 |
| last_login | TIMESTAMP(6) | 最后登录时间 |
| created_at | TIMESTAMP(6) | 创建时间 |
| updated_at | TIMESTAMP(6) | 更新时间 |

---

### t_user_role — 用户-角色关联

| 列 | 类型 | 说明 |
|----|------|------|
| username | VARCHAR(100) | 用户名（联合 PK） |
| role_name | VARCHAR(50) | 角色名（联合 PK） |
| assigned_at | TIMESTAMP(6) | 授权时间 |
| assigned_by | VARCHAR(100) | 授权人 username |

联合主键 `(username, role_name)`，**不使用 user_id**。

---

### t_data_item — 数据条目（核心，纯数据）

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 数据 ID |
| dataset_id | BIGINT | 逻辑 FK → t_dataset |
| content | TEXT | 原始文本内容（不变） |
| content_hash | VARCHAR(64) | SHA-256(content)，用于去重 |
| source | VARCHAR(50) | 来源类型（upload/api/seed） |
| source_ref | VARCHAR(255) | 来源文件名或 URL |
| status | VARCHAR(30) | 状态缓存（见状态机），加索引 |
| created_by | VARCHAR(100) | 上传人 username |
| created_at | TIMESTAMP(6) | 上传时间 |
| updated_at | TIMESTAMP(6) | 最后更新时间 |

唯一索引：`(dataset_id, content_hash)` — 同数据集内按内容去重。

#### 状态机（status 取值）

```
raw → cleaned → pre_annotated → annotated → checked
```

---

### t_data_state — 数据状态流转记录（1:1 with t_data_item）

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 状态记录 ID |
| data_id | BIGINT UNIQUE | 逻辑 FK → t_data_item（1:1） |
| stage | VARCHAR(30) | 当前阶段（与 t_data_item.status 同步） |
| updated_by | VARCHAR(100) | 最后操作人 username |
| updated_at | TIMESTAMP(6) | 最后更新时间 |

---

### t_pre_annotation — LLM 预标注历史

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 预标注 ID |
| data_id | BIGINT | 逻辑 FK → t_data_item |
| dataset_id | BIGINT | 冗余，方便按数据集查询 |
| label | VARCHAR(200) | LLM 预测标签 |
| score | FLOAT | 置信度 0-1 |
| model_name | VARCHAR(100) | 使用的模型名称 |
| version | INTEGER | 同一数据的第几次预标注 |
| created_by | VARCHAR(100) | 操作人 username |
| created_at | TIMESTAMP(6) | 预标注时间 |

---

### t_annotation — 人工标注（多人多版本）

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 标注 ID |
| data_id | BIGINT | 逻辑 FK → t_data_item |
| dataset_id | BIGINT | 冗余，方便按数据集查询 |
| username | VARCHAR(100) | 标注员 username |
| label | VARCHAR(200) | 标注结果 |
| note | TEXT | 备注（可空） |
| version | INTEGER | 同一用户对同一数据的第几次标注 |
| is_active | BOOLEAN | 是否为当前有效标注（每人只有一条 active） |
| created_at | TIMESTAMP(6) | 标注时间 |
| updated_at | TIMESTAMP(6) | 更新时间 |

索引：`(data_id, username)`，`(dataset_id, is_active)`。

**多人标注规则**：每个用户对同一 `data_id` 提交新标注时，旧标注 `is_active=false`，新标注 `version+1, is_active=true`。

---

### t_data_comment — 数据评论

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 评论 ID |
| data_id | BIGINT | 逻辑 FK → t_data_item |
| dataset_id | BIGINT | 冗余 |
| username | VARCHAR(100) | 评论人 username |
| content | TEXT | 评论内容 |
| created_at | TIMESTAMP(6) | 评论时间 |
| updated_at | TIMESTAMP(6) | 更新时间 |

---

### t_conflict — 冲突记录

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 冲突 ID |
| data_id | BIGINT | 逻辑 FK → t_data_item |
| dataset_id | BIGINT | 冗余 |
| conflict_type | VARCHAR(50) | label_conflict / semantic_conflict |
| detail | JSONB | 冲突详情（见下方结构） |
| status | VARCHAR(20) | open / resolved |
| resolved_by | VARCHAR(100) | 解决人 username（可空） |
| resolved_at | TIMESTAMP(6) | 解决时间（可空） |
| created_at | TIMESTAMP(6) | 检测时间 |

索引：`(dataset_id, status)`，`(data_id, conflict_type, status)`。

#### detail 结构

**标注冲突（label_conflict）**：
```json
{
  "conflicting_labels": ["寿险意图", "拒识"],
  "annotators": [
    {"username": "user1", "label": "寿险意图"},
    {"username": "user2", "label": "拒识"}
  ]
}
```

**语义冲突（semantic_conflict）**：
```json
{
  "similarity": 0.9341,
  "threshold": 0.9,
  "paired_id": 42,
  "paired_content": "另一条相似文本",
  "paired_label": "拒识",
  "self_label": "寿险意图"
}
```

---

### t_export_template — 导出模板

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 模板 ID |
| dataset_id | BIGINT | 逻辑 FK → t_dataset |
| name | VARCHAR(100) | 模板名称 |
| description | TEXT | 描述（可空） |
| format | VARCHAR(20) | json / excel / csv |
| columns | JSONB | 字段映射列表 |
| filters | JSONB | 过滤条件 |
| created_by | VARCHAR(100) | 创建人 username |
| created_at | TIMESTAMP(6) | 创建时间 |
| updated_at | TIMESTAMP(6) | 更新时间 |

---

### t_pipeline_status — Pipeline 运行状态（per-dataset）

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | 记录 ID |
| dataset_id | BIGINT UNIQUE | 逻辑 FK → t_dataset |
| status | VARCHAR(32) | running / completed / error / idle |
| current_step | VARCHAR(32) | process / pre_annotate / embed / check |
| progress | INTEGER | 0-100 |
| detail | JSONB | 进度详情（processed/total/speed/eta） |
| started_at | TIMESTAMP(6) | 开始时间 |
| finished_at | TIMESTAMP(6) | 结束时间 |
| updated_at | TIMESTAMP(6) | 最后更新时间 |
| error | TEXT | 错误信息（可空） |
| results | JSONB | 各步骤结果汇总（可空） |

---

## 向量文件结构（本地，不入库）

```
nas/                            ← settings.storage_path
├── embeddings/
│   └── {data_item_id}.npy      ← shape (dim,)，float32，已 L2 归一化
└── vector_index/
    ├── faiss.index             ← FAISS IndexFlatIP 文件
    └── ids.json                ← 与索引对应的 data_item_id 列表（顺序严格对应）
```

---

## DBManager 核心接口（v2.0）

`src/datapulse/repository/base.py` 的 `DBManager`：

```python
# Dataset CRUD
db.list_datasets(include_inactive)      → list[dict]
db.get_dataset(dataset_id)              → dict | None
db.create_dataset(name, description, created_by) → dict
db.update_dataset(dataset_id, patch)    → dict | None
db.delete_dataset(dataset_id)           → bool

# Config（热更新，每次查 DB）
db.get_dataset_config(dataset_id)       → dict   # deep_merge(DEFAULT, db_row)
db.set_dataset_config(dataset_id, cfg, updated_by) → None

# Data CRUD（全部按 dataset_id 隔离）
db.create_data(dataset_id, content, source, source_ref, created_by) → dict | None  # None = 重复
db.get_data(data_id, enrich)            → dict | None   # enrich=True 附加标注/预标注
db.delete_data(data_id)                 → bool
db.list_data(dataset_id, status, page, page_size) → {"total": N, "items": [...]}
db.list_by_status(dataset_id, status)   → list[dict]
db.stats(dataset_id)                    → {"total": N, "raw": N, "cleaned": N, ...}

# 状态流转
db.update_stage(data_id, stage, updated_by) → None   # 同步 t_data_state + t_data_item.status

# 预标注
db.create_pre_annotation(data_id, dataset_id, label, score, model_name, created_by) → dict
db.get_latest_pre_annotation(data_id)   → dict | None

# 人工标注（多人多版本）
db.create_annotation(data_id, dataset_id, username, label, note) → dict
db.get_active_annotations(data_id)      → list[dict]   # 每人最新一条
db.get_annotation_history(data_id)      → list[dict]   # 全部历史

# 冲突
db.create_conflict(data_id, dataset_id, conflict_type, detail) → dict
db.clear_conflicts(dataset_id)          → None
db.get_open_conflicts(data_id)          → list[dict]
db.list_conflicts_by_dataset(dataset_id, status) → list[dict]
db.resolve_conflict(conflict_id, resolved_by) → dict | None

# 评论
db.create_comment(data_id, dataset_id, username, content) → dict
db.list_comments(data_id)              → list[dict]

# Pipeline 状态
db.get_pipeline_status(dataset_id)     → dict
# （set_pipeline_status 由 pipeline.engine 内部管理）

# 用户 & 角色（RBAC）
db.list_users()                        → list[dict]
db.get_user_by_username(username)      → dict | None  # 含 password_hash
db.create_user(username, password_hash, email, role_names) → dict
db.update_user(user_id, patch)         → dict | None
db.delete_user(user_id)                → bool
db.list_roles()                        → list[dict]

# 模板
db.list_templates(dataset_id)          → list[dict]
db.get_template(template_id)           → dict | None
db.create_template(dataset_id, ...)    → dict
db.update_template(template_id, ...)   → dict | None
db.delete_template(template_id)        → bool

# 初始化（lifespan 调用）
db.seed_defaults()   # 写入预置角色 + 默认 dataset + admin 用户（幂等）
```

---

## 统一响应格式（v2.0）

所有 `/api/` 路由返回：

```json
{
  "code":      0,
  "message":   "OK",
  "data":      { ... },
  "trace_id":  "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-01-15T09:32:11.123456Z"
}
```

业务错误码：

| code | 含义 | HTTP 状态 |
|------|------|-----------|
| 0 | 成功 | 200 |
| 1001 | 参数错误 | 400 |
| 1002 | 资源不存在 | 404 |
| 1003 | 权限不足 | 403 |
| 1004 | Pipeline 正在运行 | 409 |
| 9999 | 内部服务器错误 | 500 |
