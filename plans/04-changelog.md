# 变更日志

> 记录每次重要的结构变更和决策修订，供 AI 接手者了解项目演进历史。

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
