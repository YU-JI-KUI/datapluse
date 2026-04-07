# 变更日志

> 记录每次重要的结构变更和决策修订，供 AI 接手者了解项目演进历史。

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
