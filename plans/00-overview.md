# Datapluse · 项目总览

> **面向 AI 接手者的快速上下文文档**
> 读完这个目录（plans/），你可以在 10 分钟内理解整个项目的前世今生，直接开始工作。

---

## 一句话描述

Datapluse 是一个 **AI 数据生产平台**，目标是产出可直接用于大模型训练的高质量意图识别数据集。

```
数据上传 → 清洗 → LLM 预标注 → 人工标注 → 冲突检测 → 高质量数据导出
```

---

## 背景与定位

| 项目背景 | 说明 |
|---------|------|
| 业务场景 | 保险意图识别（寿险意图 / 拒识 / 健康险意图 / 财险意图 / 其他意图） |
| 主要用户 | 数据工程师 + 标注员（多角色，RBAC 权限控制） |
| 当前阶段 | 数据生产（训练数据产出）。**不含**：模型训练、推理服务 |
| 约束条件 | 主数据存 PostgreSQL；embedding 向量存本地文件；embedding 用本地模型 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+，FastAPI，uvicorn，uv（依赖管理） |
| 前端 | React 18，Vite，Tailwind CSS，shadcn/ui 风格组件 |
| 数据库 | PostgreSQL（主存储）+ 本地文件（Embedding 向量） |
| 向量 | FAISS（可选）/ numpy 暴力检索（降级） |
| Embedding | SentenceTransformer（本地，可 mock） |
| 部署 | FastAPI 直接托管 React build 产物（单进程，单端口 8000） |

---

## 目录结构（v0.5.0）

```
datapluse/
├── plans/                    ← 项目文档（本目录），源码的一部分
│   ├── 00-overview.md        ← 本文件：项目总览
│   ├── 01-architecture.md    ← 架构决策记录（ADR）
│   ├── 02-data-model.md      ← 数据模型 & DB 表结构
│   ├── 03-api-reference.md   ← API 路由速查
│   └── 04-changelog.md       ← 变更日志
│
├── database/
│   └── init.sql              ← 手动执行的建表 DDL（含字段注释）
│
├── backend/
│   ├── main.py               ← 入口：注册路由 + 托管前端静态文件
│   ├── config/settings.py    ← 配置（仅读 DB 连接 + secret_key）
│   ├── storage/
│   │   ├── models.py         ← SQLAlchemy ORM 表模型
│   │   ├── db.py             ← DBManager（所有 DB 操作 + seed）
│   │   └── embeddings.py     ← 向量文件读写（FAISS 需要本地磁盘）
│   ├── modules/
│   │   ├── processing.py     ← 文本清洗 + 文件解析（xlsx/json/csv）
│   │   ├── model.py          ← LLM 预标注（mock + 真实接口预留）
│   │   ├── embedding.py      ← 向量编码（mock + SentenceTransformer）
│   │   ├── vector.py         ← FAISS 索引（增删查 + 持久化）
│   │   └── conflict.py       ← 冲突检测（标注冲突 + 语义冲突）
│   ├── pipeline/engine.py    ← Pipeline 4 步引擎（异步 + 进度追踪）
│   ├── api/
│   │   ├── auth.py           ← JWT 登录（RBAC，DB 用户校验）
│   │   ├── users.py          ← 用户管理 CRUD（管理员专用）
│   │   ├── datasets.py       ← 数据集 CRUD（隔离单元）
│   │   ├── data.py           ← 上传 / 列表 / 统计 / 删除
│   │   ├── pipeline.py       ← 触发 / 单步 / 状态查询
│   │   ├── annotation.py     ← 标注队列 / 提交 / 历史
│   │   ├── config.py         ← 读写配置 / 重载模型 / 重建索引
│   │   ├── export.py         ← 生成 JSON/Excel/CSV / 下载
│   │   └── templates.py      ← 导出模板 CRUD
│   └── tools/
│       ├── hash_password.py  ← 生成 bcrypt 密码哈希（工具脚本）
│       └── seed_admin.py     ← 交互式创建初始管理员
│
├── frontend/
│   ├── src/pages/            ← 9 个页面（含用户管理）
│   ├── src/components/       ← Layout（含 Dataset 选择器）+ UI 组件
│   ├── src/lib/api.js        ← axios 封装（token 注入 + dataset_id）
│   └── dist/                 ← build 产物（gitignored）
│
├── config.yaml               ← 运行时配置（gitignored！含密码）
├── config.example.yaml       ← 配置模板（提交到 git）
├── pyproject.toml
├── README.md
├── start.sh
└── build.sh
```

---

## 关键设计决策（摘要，详见 01-architecture.md）

1. **多 Dataset 隔离**：所有数据操作按 `dataset_id` 隔离，不同 dataset 独立配置、独立数据
2. **DB-backed 配置热更新**：配置存 `system_config` 表，每次读取直接查 DB，天然支持热更新
3. **RBAC 权限**：roles 表（admin/annotator/viewer）+ 权限 JSONB，JWT 携带 roles
4. **Mock 优先**：embedding 和 LLM 默认 mock，方便在没有 GPU 的环境开发
5. **单体部署**：FastAPI 托管前端静态文件，一个进程一个端口

---

## 快速启动（5 步）

```bash
# 1. 建数据库表（首次）
psql -U your-username -d datapluse -f database/init.sql

# 2. 初始化配置
cp config.example.yaml config.yaml   # 修改 DB 连接和 secret_key

# 3. 创建初始管理员
cd backend && uv run python tools/seed_admin.py

# 4. 构建前端（首次）
cd ../frontend && npm install && npm run build

# 5. 启动服务
cd .. && cd backend && uv run python main.py
# → http://localhost:8000
```
