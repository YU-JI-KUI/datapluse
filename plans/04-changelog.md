# 变更日志

> 记录每次重要的结构变更和决策修订，供 AI 接手者了解项目演进历史。

---

## v0.4.0 — 2026-04-07

### 存储层迁移：NAS → PostgreSQL

**核心重构**
- 新增 `backend/storage/models.py`：SQLAlchemy ORM 模型定义
  - `DataItem`：核心数据表（36 字段），支持 JSONB 存储冲突详情
  - `ExportTemplate`：导出模板表，columns/filters 均为 JSONB
  - `PipelineStatus`：单行流水线状态表（id=1）
- 新增 `backend/storage/db.py`：`DBManager` 替代原 `NASManager`
  - SQLAlchemy 2.0 sync 引擎 + psycopg2 driver
  - `_session()` contextmanager：自动 commit/rollback/close
  - 同等接口：`create` / `get` / `update` / `delete` / `list_all` / `list_by_status` / `stats`
  - 新增模板 CRUD：`list_templates` / `get_template` / `create_template` / `update_template` / `delete_template`
  - 导出的常量：`AVAILABLE_FIELDS`（供 API 和前端模板编辑器使用）
- 新增 `backend/storage/embeddings.py`：向量文件的最小化存储（保留文件系统，FAISS 向量无法入库）
- **删除** `backend/storage/nas.py`：完整 NAS 实现，已被 PostgreSQL 替代，清理死码
- `init_db(db_url)` 在 FastAPI startup 事件中调用，自动执行 `Base.metadata.create_all`（表不存在则建表）

**依赖更新**
- `pyproject.toml` 新增：`sqlalchemy>=2.0.0`、`psycopg2-binary>=2.9.0`
- 安装命令：`uv add sqlalchemy psycopg2-binary`

**配置更新**
- `config.example.yaml` 新增 `database` 节点：`host` / `port` / `name` / `user` / `password`
- `config/settings.py` 新增 `db_url` 属性（拼接 postgresql:// 连接串）
- `storage.base_path` 保留，仅用于 Embedding 向量文件

**所有 API / 模块更新**（`get_nas()` → `get_db()`）
- `api/data.py`、`api/annotation.py`、`api/pipeline.py`
- `pipeline/engine.py`：移除 `begin_bulk()` / `end_bulk()`（DB 事务天然支持批量）
- `modules/conflict.py`：向量操作改用 `get_emb()`
- `modules/vector.py`：所有 `get_nas()` 改为 `get_emb()`，`rebuild_index()` 用 `emb.load_all()`

---

### 导出模板系统

**后端**
- 新增 `backend/api/templates.py`：`/api/templates` 完整 CRUD 路由
  - Pydantic 模型：`ColumnDef(source, target, include)`、`TemplateFilters`、`TemplateCreate`、`TemplateUpdate`
- `api/export.py` 重写：
  - 废弃磁盘临时文件，改用 `StreamingResponse`（直接流式传输给浏览器）
  - 支持可选 `template_id` 参数，按模板列映射导出字段
  - `_apply_columns(item, columns)` 应用字段映射
  - 三种格式：`json`（带缩进）、`excel`（openpyxl）、`csv`（utf-8-sig，Excel 友好）
  - `/export/fields` 端点返回可用源字段列表

**前端**
- `frontend/src/pages/Export.jsx` 全面重写：
  - Tab 布局：「导出数据」和「模板管理」两个子页面
  - `ExportPanel`：模板下拉选择器、格式选择器（默认不用模板则按选择格式导出）、模板预览（蓝色等宽字体 `{{source}} → target` 徽章）
  - `TemplatesPanel`：模板列表（格式图标 + 字段列预览）+ 编辑 / 删除操作
  - `TemplateEditor`：名称 / 描述 / 格式 + 字段映射表（勾选框 + `{{source}}` 展示 + 可编辑 target 名称 + 删除行 + 新增字段下拉）
  - 占位符语法：`{{text}}`、`{{label}}` 等以蓝色等宽字体展示，与实际字段名区分
- `frontend/src/lib/api.js` 新增 `templateApi`（list / get / create / update / delete）

---

### 侧边栏折叠 / 展开

- `frontend/src/components/Layout.jsx`：
  - `useState` 初始值从 `localStorage.getItem('sidebar-collapsed')` 读取，刷新后保持状态
  - 展开：`w-60`，折叠：`w-16`，`transition-all duration-200` 平滑过渡
  - 折叠时导航项 `justify-center`，只显示图标，`title` 属性作为 tooltip
  - 底部切换按钮：折叠显示 `ChevronRight`，展开显示 `ChevronLeft` + "收起" 文字
  - 折叠时用户头像保留，用户名和登出按钮隐藏，鼠标悬停显示用户名 tooltip

---

## v0.3.0 — 2026-04-07

### 性能 / 体验优化

**NAS 内存索引（manifest）**
- `backend/storage/nas.py` 全量重写：启动时加载 `nas/_manifest.json` 到内存 `_index`
- `list_all()` / `stats()` 直接读内存，彻底告别 O(N) 磁盘扫描，支持 6 万+ 条数据
- `update()` / `create()` / `delete()` 同步更新内存后原子写 manifest
- Pipeline 批量写引入 `begin_bulk()` / `end_bulk()`，批量结束后统一 flush，避免每条写一次 manifest
- `get()` 优先用索引定位 status 目录，避免遍历所有目录

**Pipeline 进度增强**
- `backend/pipeline/engine.py` 每个步骤新增 `detail` 字典：`processed`（已处理数）、`total`（总数）、`skipped`（跳过数）、`pct`（百分比字符串）、`speed_per_sec`（每秒条数）、`eta_seconds`（预计剩余秒数）、`elapsed_seconds`（已用时）
- 前端 Pipeline 状态接口可直接展示进度条 + 速度 + ETA

**上海时区统一**
- 引入 `ZoneInfo("Asia/Shanghai")`，统一 `_now()` 函数：`datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")`
- 替换所有 `datetime.utcnow().isoformat()` 调用：`nas.py`、`engine.py`、`api/annotation.py`、`api/export.py`
- JWT `exp` 字段保持 UTC（符合 RFC 7519 标准，不受影响）
- 新增 `tzdata>=2023.3` 依赖（Windows 无内置时区数据库时需要）

**前端 DataManagement 白屏修复**
- `statusFilter` 初始值从 `''` 改为 `'all'`：Radix UI Select 不接受空字符串 value，会导致白屏
- `STATUS_OPTIONS` 第一项 value 改为 `'all'`，API 调用时将 `'all'` 转换为 `undefined`（不传 status 参数）
- 数据列表 query 增加 `staleTime: 0`：从其他页面返回时立即重新拉取，不再看到 30 秒内的旧缓存
- 删除未使用的 `Search`、`FileText` lucide-react 导入

**nas/ 目录结构入库**
- 更新 `.gitignore`：从 `nas/` 整体忽略改为按子目录精确控制
  - `raw/*.json` 忽略，但 `raw/example_*.json` 用 `!` 反向保留
  - 其余运行时产物（embeddings、export、_manifest.json 等）仍忽略
- 新增 `nas/README.md`：数据格式文档、目录说明、如何准备数据
- 新增 `nas/raw/example_insurance_queries.json`：15 条保险意图识别示例，可直接上传体验

---

## v0.2.0 — 2026-04-07

### 变更
- **项目根目录重组**：移除 `Datapluse/` 子目录，所有文件直接放在 workspace 根目录
- **依赖管理迁移**：从 `requirements.txt` + pip 迁移至 `pyproject.toml` + **uv**
  - 核心依赖：`uv sync`
  - 可选组：`--extra faiss`（FAISS 向量检索）、`--extra embedding`（本地模型）
- **敏感配置分离**：
  - `config.yaml`（含密码）加入 `.gitignore`，不入库
  - 新增 `config.example.yaml`（密码替换为占位符），作为模板提交
- **运行时数据隔离**：`nas/` 目录加入 `.gitignore`，由 `start.sh` 在运行时自动创建
- **新增 `.gitignore`**：覆盖 Python、前端构建、NAS 数据、敏感配置
- **新增 `plans/` 目录**：架构决策文档，作为源码一部分入库

### 删除
- `requirements.txt`：被 `pyproject.toml` 完全替代，删除避免 AI 混淆
- `main.py`（根目录）：`uv init` 自动生成的存根，无实际作用
- `Datapluse/` 子目录：内容已迁移到根目录

---

## v0.1.0 — 2026-04-07

### 初始实现

**整体架构**：FastAPI + React SPA 单体部署，NAS 文件系统存储。

**后端模块**（共 14 个 Python 文件）：
- `backend/main.py`：FastAPI 入口，注册 6 个路由，托管前端静态文件
- `backend/config/settings.py`：配置单例，支持热更新
- `backend/storage/nas.py`：NAS 文件系统 CRUD 层
- `backend/modules/processing.py`：文本清洗 + xlsx/json/csv 解析
- `backend/modules/model.py`：LLM 预标注（mock + 真实接口预留）
- `backend/modules/embedding.py`：向量编码（mock + SentenceTransformer）
- `backend/modules/vector.py`：FAISS 索引（可降级 numpy）
- `backend/modules/conflict.py`：标注冲突 + 语义冲突检测
- `backend/pipeline/engine.py`：4 步 Pipeline 引擎
- `backend/api/{auth,data,pipeline,annotation,config,export}.py`：6 个路由

**前端**（React 18 + Vite + Tailwind）：
- 8 个页面：Dashboard / 数据管理 / 预标注 / 标注 / 冲突检测 / 配置中心 / 导出 / 登录
- 7 个 shadcn/ui 风格基础组件
- `src/lib/api.js`：统一 axios 封装（token 注入 + 401 跳转）

**关键约束**：
- 禁止数据库：所有数据存 JSON 文件
- 禁止外部 embedding API：使用本地模型（可 mock）
- 单体部署：FastAPI 直接 serve `frontend/dist/`
