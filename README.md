# Datapluse · 数据飞轮

> AI 数据生产平台：数据采集 → 预标注 → 人工标注 → 冲突检测 → 高质量数据导出

---

## 快速启动

### 0. 安装 uv（如未安装）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. 构建前端（首次运行）

```bash
cd frontend
npm install
npm run build
cd ..
```

### 2. 同步 Python 依赖

```bash
# 安装核心依赖（自动创建 .venv）
uv sync

# 安装可选依赖
uv sync --extra faiss      # FAISS 向量检索（推荐）
uv sync --extra embedding  # 本地 Embedding 模型（use_mock=false 时需要）
uv sync --extra all        # 全量安装
```

### 3. 启动 Web 服务

```bash
cd backend
uv run python main.py
# 访问 http://localhost:8000
# 默认账号: admin / datapluse2024
```

> 开发模式：前端 `npm run dev`（端口 5173）同时运行，API 代理到 8000

---

## 项目结构

```
Datapluse/
├── config.yaml          # 全局配置（可视化编辑）
├── requirements.txt
├── start.sh / build.sh
│
├── backend/
│   ├── main.py          # FastAPI + 静态文件托管
│   ├── config/
│   │   └── settings.py  # 配置读写（单例）
│   ├── storage/
│   │   └── nas.py       # NAS 文件系统 CRUD
│   ├── modules/
│   │   ├── processing.py  # 数据清洗
│   │   ├── model.py       # LLM 预标注（mock + 真实接口预留）
│   │   ├── embedding.py   # 本地 Embedding（mock + SentenceTransformer）
│   │   ├── vector.py      # FAISS 向量索引
│   │   └── conflict.py    # 冲突检测（标注 + 语义）
│   ├── pipeline/
│   │   └── engine.py    # Pipeline 引擎（process→pre_annotate→embed→check）
│   └── api/
│       ├── auth.py      # JWT 认证
│       ├── data.py      # 数据上传/查询
│       ├── pipeline.py  # Pipeline 触发/状态
│       ├── annotation.py # 标注 CRUD
│       ├── config.py    # 配置读写 API
│       └── export.py    # 导出 JSON/Excel
│
├── frontend/            # React + shadcn/ui + Tailwind
│   └── src/pages/
│       ├── Dashboard.jsx        # 统计概览 + Pipeline 状态
│       ├── DataManagement.jsx   # 上传 + 数据列表
│       ├── PreAnnotation.jsx    # LLM 预标注
│       ├── Annotation.jsx       # 翻牌式人工标注
│       ├── ConflictDetection.jsx # 冲突检测 + 审核
│       ├── ConfigCenter.jsx     # 可视化参数配置
│       └── Export.jsx           # 导出高质量数据
│
└── nas/                 # NAS 数据目录
    ├── raw/             # 原始数据
    ├── processed/       # 清洗后
    ├── pre_annotated/   # 预标注后
    ├── labeled/         # 人工标注后
    ├── checked/         # 通过冲突检测
    ├── embeddings/      # 向量文件
    ├── vector_index/    # FAISS 索引
    └── export/          # 导出文件
```

---

## 接入真实 LLM 平台

修改 `backend/modules/model.py` 中的 `_call_real_llm()` 函数，并在 `config.yaml` 中设置：

```yaml
llm:
  use_mock: false
  api_url: "http://your-internal-platform/api/v1/chat"
  model_name: "your-model"
```

## 接入本地 Embedding 模型

安装依赖：
```bash
uv sync --extra embedding
```

修改 `config.yaml`：
```yaml
embedding:
  use_mock: false
  model_path: "/path/to/bge-base-zh"
```

在配置中心点击"重载模型"即可生效。

---

## API 文档

启动后访问：http://localhost:8000/api/docs
