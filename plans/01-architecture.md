# 架构决策记录（ADR）

> 记录每一个"为什么这样做"，而不只是"做了什么"。

---

## ADR-001：存储层 — PostgreSQL 主数据库

**决策**：v0.4.0 起，主数据存 PostgreSQL（SQLAlchemy ORM + psycopg2）；Embedding 向量文件保留本地文件系统（FAISS 必须本地磁盘）。

**背景**：
- v0.1~0.3 曾用 NAS 文件系统（JSON 文件），大数据量下扫描慢，无事务，并发写有冲突风险
- 实际部署有 PostgreSQL 可用，切换成本低
- 需要支持多用户 + RBAC，文件系统无法做行级隔离

**实现方式**：
- `storage/models.py`：SQLAlchemy ORM 表模型
- `storage/db.py`：`DBManager` 单例，封装所有 CRUD 操作
- `init_db(db_url)` 在 FastAPI startup 事件中调用；正式建表推荐使用 `database/init.sql`

**权衡**：
- ✅ 支持并发、事务、复杂查询
- ✅ 可独立备份、迁移
- ✅ 支持多 Dataset 行级隔离
- ❌ 需要 PostgreSQL 服务（本地或远程）

---

## ADR-002：多 Dataset 隔离

**决策**：v0.5.0 引入 `datasets` 表作为顶级隔离单元。每个 dataset 拥有独立的数据条目、pipeline 状态、配置和导出模板。

**实现方式**：
- `data_items.dataset_id`、`pipeline_status.dataset_id`、`system_config.dataset_id`、`export_templates.dataset_id` 均关联 `datasets.id`
- 所有 API 端点通过 `dataset_id: str = Query(...)` 强制传入 dataset 上下文
- 前端 Layout 侧边栏提供 Dataset 选择器，存 `localStorage`

---

## ADR-003：配置中心 — DB-backed 热更新

**决策**：v0.5.0 将所有业务配置（llm / embedding / similarity / pipeline / labels）迁移到 `system_config` 表（每个 dataset 独立一行 JSONB config_data）。

**热更新机制**：
- `db.get_dataset_config(dataset_id)` 每次调用直接查 DB，无内存缓存
- 配置中心 UI 保存后立即生效，无需重启服务
- `DEFAULT_DATASET_CONFIG` 作为 base，`_deep_merge(base, db_row)` 提供默认值兜底

**config.yaml 简化**：仅保留 bootstrap 参数（db_url, storage_base_path, secret_key），以及兼容迁移的 `legacy_admin_*`。

---

## ADR-004：RBAC 用户权限

**决策**：v0.5.0 引入完整 RBAC，用户信息存 DB，废弃 config.yaml 中的 admin 账号配置。

**模型**：`users` → `user_roles` → `roles（name + permissions JSONB）`

**预置角色**：
| 角色 | 权限 |
|------|------|
| admin | `["*"]`（所有权限） |
| annotator | `["annotation:read", "annotation:write", "data:read"]` |
| viewer | `["annotation:read", "data:read"]` |

**JWT payload**：包含 `user_id`、`sub`（username）、`roles` 数组。

**初始化**：`tools/seed_admin.py` 交互式创建第一个管理员；`tools/hash_password.py` 生成 bcrypt 哈希。

**兼容迁移**：如果 config.yaml 中存在 `legacy_admin_*`，服务启动时自动创建管理员（幂等）。

---

## ADR-005：数据状态机

**状态流转**：

```
raw → processed → pre_annotated → labeling → labeled → checked
                                                           ↓
                                                        export
```

- `raw`：刚上传，未清洗
- `processed`：文本清洗完成
- `pre_annotated`：LLM 已预测标签（model_pred + model_score）
- `labeling`：某标注员已"取走"，标注中（防止多人重复标注同一条）
- `labeled`：人工标注完成（label + annotator + annotated_at）
- `checked`：通过冲突检测，高质量数据，可导出

**注意**：`conflict_flag=True` 的数据保留在 `labeled` 状态，等待人工复核后手动提升为 `checked`。

---

## ADR-006：Pipeline 引擎设计

**4 个步骤**：`process → pre_annotate → embed → check`

**设计原则**：
1. 每步操作**幂等**：重复运行不会破坏数据（已处理的数据跳过）
2. 步骤间**松耦合**：可单独运行任意步骤
3. 每步接受 `dataset_id`，操作范围严格限制在该 dataset 内
4. 配置通过 `cfg = db.get_dataset_config(dataset_id)` 动态读取，支持热更新

**并发模式**：
- `POST /pipeline/run` → FastAPI `BackgroundTasks`，非阻塞
- `POST /pipeline/run-step` → 同步执行，适合调试

**进度追踪**：前端每 3 秒 poll `GET /pipeline/status?dataset_id=xxx`，显示进度条 + ETA。

---

## ADR-007：冲突检测算法

**类型 1：标注冲突（Label Conflict）**

```python
# 同一文本 text 被不同 annotator 标注了不同 label
group_by(text) → find groups where len(unique labels) > 1
```

**类型 2：语义冲突（Semantic Conflict）**

```python
# cosine_similarity(vec_A, vec_B) > threshold AND label_A != label_B
```

- 触发条件：相似度 > `cfg["similarity"]["threshold_high"]`（默认 0.9）
- 使用 FAISS 加速检索（退化为 numpy 暴力时 O(N²)）

---

## ADR-008：Embedding 模块设计（Mock 优先）

| 模式 | 实现 | 适用场景 |
|------|------|---------|
| `use_mock: true` | 基于 text hash 的确定性随机单位向量 | 开发/演示（无需 GPU） |
| `use_mock: false` | SentenceTransformer 本地加载 | 生产（需配置 model_path） |

**cfg 传参**：`embed_text(text, cfg)` / `embed_batch(texts, cfg)` 通过 cfg dict 读配置，不依赖全局 settings 单例，支持 per-dataset 配置热更新。

---

## ADR-009：前端页面设计

| 路由 | 页面 | 核心功能 |
|------|------|---------|
| `/dashboard` | Dashboard | 统计卡片 + Bar Chart + Pipeline 状态 |
| `/data` | 数据管理 | 拖拽上传（xlsx/json/csv）+ 列表 + 状态过滤 |
| `/pre-annotation` | 预标注 | 触发 pre_annotate 步骤 + 结果列表 |
| `/annotation` | 标注 | 翻牌式（Next → 展示文本 → 点击标签即提交）|
| `/conflicts` | 冲突检测 | 运行 check + 分类展示冲突 + 逐条审核 |
| `/config` | 配置中心 | Dataset 级 JSONB 配置编辑 + 保存 |
| `/export` | 导出 | 模板选择 + 格式选择 + 下载 |
| `/users` | 用户管理 | 用户 CRUD + 角色分配（管理员专用）|
| `/login` | 登录 | JWT 表单登录 |

**Dataset 切换**：Layout 侧边栏顶部 Dataset 选择器，切换时广播 `datasetChanged` 自定义事件，各页面监听并刷新数据。

**Auth 流程**：`localStorage` 存 `token` + `username` + `roles` → axios interceptor 自动附加 → 401 跳 `/login`；`/users` 路由加 `RequireAdmin` 守卫。

---

## 技术债务

| 项目 | 风险 | 建议 |
|------|------|------|
| 标注"取走"机制弱 | `labeling` 状态无超时回收 | 加定时任务清理超时 labeling 条目 |
| Pipeline 异步无中断机制 | 无法取消正在运行的 Pipeline | 引入 asyncio.Task + cancel |
| has_permission 每次查 DB | 高频接口有多余查询 | 可将 permissions 缓存在 JWT 或加短 TTL cache |
| 前端 dataset_id 未全部注入 | 部分旧页面可能未传 dataset_id | 逐页检查，统一从 getCurrentDatasetId() 读取 |
