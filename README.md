# Datapulse · 数据飞轮

> AI 数据生产平台：数据上传 → 清洗 → LLM 预标注 → 人工标注 → 冲突检测 → 高质量数据导出

**v0.5.0** · FastAPI + React · PostgreSQL 主存储 · 支持意图识别等分类任务

---

## 快速启动

### 前置要求

- Python 3.10+，已安装 [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- 可访问的 PostgreSQL 实例（公司内网或自建均可）

### 1. 配置

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入 PostgreSQL 连接信息和业务参数：

```yaml
database:
  host: "your-pg-hostname"
  port: 5432
  name: "datapulse"
  user: "your-username"
  password: "your-password"

auth:
  admin_username: "admin"
  admin_password: "your-password"
  secret_key: "your-secret-key"
```

首次启动时会自动建表，无需手动执行 DDL。

### 2. 安装依赖

```bash
# 安装核心依赖（自动创建 .venv）
uv sync

# 可选：FAISS 向量检索（推荐，没有则退化为 numpy 暴力搜索）
uv add faiss-cpu

# 可选：本地 Embedding 模型（use_mock=false 时需要）
uv add sentence-transformers torch
```

### 3. 构建前端（首次运行或前端有变更时）

```bash
cd frontend && npm install && npm run build && cd ..
```

### 4. 启动后端服务

```bash
# 开发模式（热重载）
uv run uvicorn datapulse.main:app --reload --reload-dir src

# 或直接运行入口模块
uv run python -m datapulse.main
```

访问 `http://localhost:8000`，账号密码见 `config.yaml` 中的 `admin_username / admin_password`。

> **前端开发模式**：`cd frontend && npm run dev`（端口 5173），API 自动代理到 8000。

### 5. 初始化管理员（可选）

如需手动创建或重置管理员账号：

```bash
uv run python -m datapulse.tools.seed_admin
```

---

## 项目结构

```
datapluse/
├── config.yaml              # 运行时配置（不入库）
├── config.example.yaml      # 配置模板（入库）
├── pyproject.toml           # Python 依赖 + ruff 规则（uv 管理）
│
├── src/
│   └── datapulse/           # Python 包根（src layout）
│       ├── main.py          # FastAPI 入口，托管 API + 前端静态文件
│       │
│       ├── api/             # ① HTTP 路由层：接收请求，调用 service
│       │   ├── auth.py      #   JWT 认证 / 登录
│       │   ├── data.py      #   数据上传 / 查询 / 删除
│       │   ├── datasets.py  #   数据集 CRUD
│       │   ├── pipeline.py  #   Pipeline 触发 / 状态查询
│       │   ├── annotation.py#   标注队列 / 提交
│       │   ├── config.py    #   配置读写
│       │   ├── export.py    #   数据导出（流式返回）
│       │   ├── templates.py #   导出模板 CRUD
│       │   └── users.py     #   用户管理
│       │
│       ├── service/         # ② 业务逻辑层：编排 repository，处理业务规则
│       │   ├── data_service.py
│       │   ├── dataset_service.py
│       │   ├── user_service.py
│       │   ├── config_service.py
│       │   ├── pipeline_service.py
│       │   └── template_service.py
│       │
│       ├── repository/      # ③ 数据访问层：所有 SQL 操作
│       │   ├── base.py      #   Session 管理，get_db()，init_db()
│       │   ├── data_repository.py
│       │   ├── dataset_repository.py
│       │   ├── user_repository.py
│       │   ├── config_repository.py
│       │   ├── pipeline_repository.py
│       │   ├── template_repository.py
│       │   └── embeddings.py#   向量文件存储（FAISS / numpy）
│       │
│       ├── model/           # ④ 模型层：SQLAlchemy ORM 表定义
│       │   └── entities.py  #   DataItem, Dataset, User, Role, …
│       │
│       ├── middleware/
│       │   └── access_log.py# 访问日志：method/path/params/body/status/耗时
│       │
│       ├── modules/         # ML 功能模块（独立，不依赖其他层）
│       │   ├── processing.py#   数据清洗 + 文件解析（xlsx/json/csv）
│       │   ├── model.py     #   LLM 预标注（mock / 真实接口）
│       │   ├── embedding.py #   向量编码（mock / SentenceTransformer）
│       │   ├── vector.py    #   FAISS 向量索引
│       │   └── conflict.py  #   冲突检测（标注冲突 + 语义冲突）
│       │
│       ├── pipeline/
│       │   └── engine.py    # Pipeline 引擎（4 步 + 进度追踪）
│       │
│       ├── config/
│       │   └── settings.py  # 配置单例（读取 config.yaml）
│       │
│       └── tools/
│           ├── hash_password.py  # 命令行：生成 bcrypt hash
│           └── seed_admin.py     # 命令行：初始化管理员账号
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Layout.jsx           # 主布局（侧边栏可折叠）
│       │   └── ui/                  # shadcn/ui 基础组件
│       ├── lib/
│       │   └── api.js               # axios 封装（token + 导出 blob）
│       └── pages/
│           ├── Dashboard.jsx        # 统计概览 + Pipeline 状态
│           ├── DataManagement.jsx   # 上传 + 数据列表（分页 + 状态过滤）
│           ├── PreAnnotation.jsx    # LLM 预标注触发
│           ├── Annotation.jsx       # 翻牌式人工标注
│           ├── ConflictDetection.jsx# 冲突检测结果 + 人工审核
│           ├── ConfigCenter.jsx     # 可视化参数配置
│           └── Export.jsx           # 数据导出 + 模板管理
│
├── nas/                     # 本地向量文件（不入 PostgreSQL）
│   ├── embeddings/          # 向量文件（{item_id}.npy）
│   ├── vector_index/        # FAISS 索引文件
│   └── raw/
│       └── example_insurance_queries.json  # 15 条保险示例数据
│
└── plans/                   # 架构文档
    ├── 00-overview.md
    ├── 01-architecture.md
    ├── 02-data-model.md
    ├── 03-api-reference.md
    └── 04-changelog.md
```

### IDE 配置（解决"Unresolved reference"）

在 PyCharm / VSCode 中将 `src/` 目录标记为 **Sources Root**：

- **PyCharm**：右键 `src/` → Mark Directory as → Sources Root
- **VSCode**：在 `.vscode/settings.json` 中添加：
  ```json
  { "python.analysis.extraPaths": ["src"] }
  ```

---

## 数据流

```
上传文件（xlsx/json/csv）
    ↓ [Pipeline: process]      文本清洗，写入 DB，status=processed
    ↓ [Pipeline: pre_annotate] LLM 批量预测，status=pre_annotated
    ↓ [Pipeline: embed]        向量编码，写入 nas/embeddings/
    ↓ [Pipeline: check]        冲突检测（标注冲突 + 语义冲突）
    ↓
人工标注（翻牌式） → status=labeled
    ↓
冲突审核 → 通过则 status=checked
    ↓
导出（JSON / Excel / CSV，按模板字段映射，流式返回）
```

---

## 接入真实 LLM

修改 `config.yaml`：

```yaml
llm:
  use_mock: false
  api_url: "http://your-internal-platform/api/v1/chat"
  model_name: "your-model"
```

并实现 `src/datapulse/modules/model.py` 中的 `_call_real_llm()` 函数。

---

## 接入本地 Embedding 模型

```bash
uv add sentence-transformers torch
```

修改 `config.yaml`：

```yaml
embedding:
  use_mock: false
  model_path: "/path/to/bge-base-zh"
```

在配置中心点击「重载模型」生效。

---

## API 文档

启动后访问：<http://localhost:8000/api/docs>

每个 API 请求均会打印访问日志（method、path、入参、返回状态、耗时），格式：

```
[ACCESS] POST /api/auth/login | params={} | body={"username":"admin"...} | 200 | 23ms
```

---

## 数据库表结构

| 表名 | 用途 |
|------|------|
| `data_items` | 核心数据（文本 + 标注 + 状态 + 冲突信息） |
| `datasets` | 数据集（多租户隔离） |
| `export_templates` | 导出模板（字段映射 + 格式 + 过滤条件） |
| `pipeline_status` | Pipeline 运行状态 |
| `users / roles / user_roles` | RBAC 权限体系 |
| `system_config` | 系统配置（JSON，按 dataset 隔离） |

首次启动时自动建表，无需手动 DDL。

---

## 代码规范

项目使用 [ruff](https://docs.astral.sh/ruff/) 统一 lint 和格式化：

```bash
# 检查并自动修复
ruff check --fix src/

# 格式化
ruff format src/
```

规则配置见 `pyproject.toml` 中的 `[tool.ruff]` 节。
