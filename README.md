# Datapluse · 数据飞轮

> AI 数据生产平台：数据上传 → 清洗 → LLM 预标注 → 人工标注 → 冲突检测 → 高质量数据导出

**v0.4.0** · FastAPI + React · PostgreSQL 主存储 · 支持意图识别等分类任务

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
  name: "datapluse"
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

### 3. 构建前端（首次运行）

```bash
cd frontend && npm install && npm run build && cd ..
```

### 4. 启动服务

```bash
cd backend && uv run python main.py
# 访问 http://localhost:8000
# 账号密码见 config.yaml 中的 admin_username / admin_password
```

> 前端开发模式：`npm run dev`（端口 5173），API 自动代理到 8000。

---

## 项目结构

```
datapluse/
├── config.yaml              # 运行时配置（不入库）
├── config.example.yaml      # 配置模板（入库）
├── pyproject.toml           # Python 依赖（uv 管理）
├── start.sh / build.sh      # 一键启停脚本
│
├── backend/
│   ├── main.py              # FastAPI 入口，托管 API + 前端静态文件
│   ├── config/
│   │   └── settings.py      # 配置单例（支持热更新）
│   ├── storage/
│   │   ├── models.py        # SQLAlchemy ORM 模型
│   │   ├── db.py            # DBManager：PostgreSQL CRUD 层
│   │   └── embeddings.py    # EmbeddingStore：向量文件（本地，FAISS 需要）
│   ├── modules/
│   │   ├── processing.py    # 数据清洗 + 文件解析（xlsx/json/csv）
│   │   ├── model.py         # LLM 预标注（mock / 真实接口）
│   │   ├── embedding.py     # 向量编码（mock / SentenceTransformer）
│   │   ├── vector.py        # FAISS 向量索引（无 FAISS 时退化 numpy）
│   │   └── conflict.py      # 冲突检测（标注冲突 + 语义冲突）
│   ├── pipeline/
│   │   └── engine.py        # Pipeline 引擎（4 步 + 进度追踪）
│   └── api/
│       ├── auth.py          # JWT 认证
│       ├── data.py          # 数据上传 / 查询 / 删除
│       ├── pipeline.py      # Pipeline 触发 / 状态查询
│       ├── annotation.py    # 标注队列 / 提交 / 批量
│       ├── config.py        # 配置读写
│       ├── export.py        # 数据导出（JSON / Excel / CSV，流式返回）
│       └── templates.py     # 导出模板 CRUD
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Layout.jsx           # 主布局（侧边栏可折叠）
│       │   └── ui/                  # shadcn/ui 基础组件
│       ├── lib/
│       │   └── api.js               # axios 封装（token + 导出 blob）
│       └── pages/
│           ├── Dashboard.jsx        # 统计概览 + Pipeline 状态/进度
│           ├── DataManagement.jsx   # 上传 + 数据列表（分页 + 状态过滤）
│           ├── PreAnnotation.jsx    # LLM 预标注触发
│           ├── Annotation.jsx       # 翻牌式人工标注
│           ├── ConflictDetection.jsx # 冲突检测结果 + 人工审核
│           ├── ConfigCenter.jsx     # 可视化参数配置
│           └── Export.jsx           # 数据导出 + 模板管理
│
├── nas/                     # 仅存放本地向量文件（数据在 PostgreSQL）
│   ├── embeddings/          # 向量文件（{item_id}.npy）
│   ├── vector_index/        # FAISS 索引文件
│   └── raw/
│       └── example_insurance_queries.json  # 15 条保险示例数据，可直接上传体验
│
└── plans/                   # 架构文档（AI 接手时阅读）
    ├── 00-overview.md
    ├── 01-architecture.md
    ├── 02-data-model.md
    ├── 03-api-reference.md
    └── 04-changelog.md
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

所有数据状态存储在 PostgreSQL `data_items` 表，向量文件存储在本地 `nas/embeddings/`。

---

## 导出模板

在「导出」页面的「模板管理」子页面创建模板，支持：

- **字段映射**：`{{source_field}}` → 自定义输出字段名（如 `text` → `sentence`）
- **按需包含字段**：勾选/取消需要导出的字段
- **格式**：JSON / Excel / CSV
- **过滤条件**：按状态筛选、是否包含冲突数据

模板保存在 PostgreSQL `export_templates` 表，随时增删改。

---

## 接入真实 LLM

修改 `config.yaml`：

```yaml
llm:
  use_mock: false
  api_url: "http://your-internal-platform/api/v1/chat"
  model_name: "your-model"
```

并实现 `backend/modules/model.py` 中的 `_call_real_llm()` 函数。

---

## 接入本地 Embedding 模型

安装依赖：

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

---

## 数据库表结构

| 表名 | 用途 |
|------|------|
| `data_items` | 核心数据（文本 + 标注 + 状态 + 冲突信息） |
| `export_templates` | 导出模板（字段映射 + 格式 + 过滤条件） |
| `pipeline_status` | Pipeline 运行状态（单行，id=1） |

首次启动时自动建表，无需手动 DDL。
