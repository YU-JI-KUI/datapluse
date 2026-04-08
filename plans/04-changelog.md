# 变更日志

> 记录每次重要的结构变更和决策修订，供 AI 接手者了解项目演进历史。

---

## v0.5.0 — 2026-04-08

### 多 Dataset 隔离 + RBAC + DB 配置中心

**核心架构变更**

- **多 Dataset 支持**：新增 `datasets` 表作为顶级隔离单元
  - `data_items`、`pipeline_status`、`system_config`、`export_templates` 全部新增 `dataset_id` 外键
  - 所有 API 端点通过 `dataset_id: str = Query(...)` 传入 dataset 上下文
  - 前端 Layout 侧边栏新增 Dataset 选择器（从 DB 拉取列表，存 localStorage）

- **RBAC 用户模块**：完整角色权限控制，废弃 config.yaml 中的 admin 账号配置
  - 新增表：`users`、`roles`、`user_roles`
  - 预置角色：admin（`["*"]`）/ annotator / viewer
  - JWT payload 新增 `user_id`、`roles` 字段
  - 新增 `backend/api/users.py`：用户 CRUD（管理员专用）
  - 新增 `backend/tools/hash_password.py`：生成 bcrypt 密码哈希
  - 新增 `backend/tools/seed_admin.py`：交互式创建初始管理员
  - 兼容迁移：config.yaml 中如果存在 `legacy_admin_*`，服务启动时自动创建管理员（幂等）

- **DB-backed 配置热更新**：业务配置迁移到 `system_config` 表（每个 dataset 独立 JSONB 行）
  - `db.get_dataset_config(dataset_id)` 每次调用直接查 DB，天然支持热更新
  - `DEFAULT_DATASET_CONFIG` 提供默认值，`_deep_merge(base, db_row)` 确保字段兜底
  - `backend/api/config.py` 重写：读写 DB 而非 YAML

- **DDL 脚本**：新增 `database/init.sql`
  - 完整建表 DDL，含每张表/每个列的 `COMMENT ON` 详细说明
  - 手动执行（不自动运行），替代 SQLAlchemy `create_all` 方式
  - 内置 `INSERT ... ON CONFLICT DO NOTHING` 预置角色和默认数据集

**后端变更**

- `backend/storage/models.py` 重写：新增 `Dataset`、`SystemConfig`、`Role`、`User`、`UserRole`；`DataItem` 新增 `dataset_id`；`PipelineStatus` 主键改为 `dataset_id`
- `backend/storage/db.py` 重写：新增 Dataset CRUD、SystemConfig get/set、User CRUD、Role 列表、`seed_defaults()`、`seed_admin_from_yaml()`；所有数据操作方法新增 `dataset_id` 参数
- `backend/config/settings.py` 简化：仅保留 `db_url`、`storage_base_path`、`secret_key`、`legacy_admin_*`（兼容迁移）
- `backend/api/auth.py` 重写：查 DB 验密码（bcrypt），JWT 携带 roles，新增 `UserInfo`、`require_admin`、`has_permission()`
- `backend/api/datasets.py`（新增）：`/api/datasets` 完整 CRUD
- `backend/api/users.py`（新增）：`/api/users` CRUD + `/roles`
- `backend/api/data.py`：新增 `dataset_id` Query 参数
- `backend/api/annotation.py`：新增 `dataset_id` Query 参数
- `backend/api/pipeline.py`：`RunStepRequest` 新增 `dataset_id`；全部传给 engine
- `backend/api/export.py`：`ExportRequest` 新增 `dataset_id`
- `backend/api/templates.py`：`list_templates` 新增 `dataset_id` Query 参数
- `backend/pipeline/engine.py` 重写：所有函数新增 `dataset_id` 参数；读 cfg 改为 `db.get_dataset_config(dataset_id)`
- `backend/modules/model.py` 重写：`pre_annotate(item, cfg)` 接受 cfg dict 不再依赖全局 settings
- `backend/modules/embedding.py` 重写：`embed_text(text, cfg)` 接受 cfg dict
- `backend/modules/conflict.py`：`detect_semantic_conflicts(dataset_id, items, cfg)` 新增 dataset/cfg 参数
- `backend/main.py` 更新：注册 datasets/users 路由；startup 调用 `seed_defaults()` + `seed_admin_from_yaml()`；版本 → 0.5.0

**前端变更**

- `frontend/src/lib/api.js`：新增 `datasetApi`、`userApi`；`dataApi`/`pipelineApi`/`annotationApi`/`configApi`/`exportApi`/`templateApi` 全部新增 `dataset_id` 参数；新增 `getCurrentDatasetId()`/`setCurrentDatasetId()`
- `frontend/src/components/Layout.jsx`：新增 Dataset 选择器（侧边栏顶部）；角色显示（admin/annotator/viewer）；"用户管理"仅对 admin 显示
- `frontend/src/pages/Users.jsx`（新增）：用户管理页（CRUD + 重置密码 + 角色卡片说明）
- `frontend/src/App.jsx`：新增 `/users` 路由 + `RequireAdmin` 守卫
- `frontend/src/pages/Login.jsx`：登录成功后存 `roles` 到 localStorage

**配置变更**

- `config.example.yaml`：移除 `embedding`、`similarity`、`pipeline`、`llm`、`labels`（迁移到 DB）；`auth` 节点仅保留 `secret_key`

---

## v0.4.0 — 2026-04-07

### 存储层迁移：NAS → PostgreSQL

**核心重构**
- 新增 `backend/storage/models.py`：SQLAlchemy ORM 模型定义
  - `DataItem`：核心数据表，支持 JSONB 存储冲突详情
  - `ExportTemplate`：导出模板表，columns/filters 均为 JSONB
  - `PipelineStatus`：单行流水线状态表（id=1）
- 新增 `backend/storage/db.py`：`DBManager` 替代原 `NASManager`
  - SQLAlchemy 2.0 sync 引擎 + psycopg2 driver
  - 同等接口：`create` / `get` / `update` / `delete` / `list_all` / `list_by_status` / `stats`
  - 新增模板 CRUD
- 新增 `backend/storage/embeddings.py`：向量文件最小化存储
- **删除** `backend/storage/nas.py`
- `init_db(db_url)` 在 FastAPI startup 事件中调用

**导出模板系统**
- 新增 `backend/api/templates.py`：`/api/templates` 完整 CRUD
- `api/export.py` 重写：`StreamingResponse` 直接流式传输；支持 `template_id` 参数；三种格式（json/excel/csv）
- `frontend/src/pages/Export.jsx` 全面重写：Tab 布局（导出数据 + 模板管理）；`TemplateEditor` 字段映射表

**侧边栏折叠**
- `Layout.jsx`：折叠状态持久化到 localStorage；折叠 / 展开平滑过渡

---

## v0.3.0 — 2026-04-07

### 性能 / 体验优化

- **NAS 内存索引**：启动时加载 `_manifest.json` 到内存，list/stats 直接读内存（O(1) vs O(N)）
- **Pipeline 进度增强**：新增 `speed_per_sec`、`eta_seconds`、`elapsed_seconds` 等详情字段
- **上海时区统一**：`ZoneInfo("Asia/Shanghai")` 替代 `datetime.utcnow()`
- **前端 DataManagement 白屏修复**：statusFilter 初始值问题

---

## v0.2.0 — 2026-04-07

### 工程规范化

- 项目根目录重组（移除子目录层级）
- 依赖管理迁移：`requirements.txt` + pip → `pyproject.toml` + **uv**
- 敏感配置分离：`config.yaml` gitignore，新增 `config.example.yaml`
- 新增 `plans/` 文档目录

---

## v0.1.0 — 2026-04-07

### 初始实现

FastAPI + React SPA 单体部署，NAS 文件系统存储。

- 后端：14 个 Python 文件（6 个路由 + 5 个算法模块 + pipeline 引擎 + 存储层 + 配置）
- 前端：8 个页面（Dashboard / 数据管理 / 预标注 / 标注 / 冲突检测 / 配置中心 / 导出 / 登录）
- Pipeline 4 步引擎：process → pre_annotate → embed → check
