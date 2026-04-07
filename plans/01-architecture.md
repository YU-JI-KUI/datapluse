# 架构决策记录（ADR）

> 记录每一个"为什么这样做"，而不只是"做了什么"。

---

## ADR-001：存储层选型 — NAS 文件系统，禁用数据库

**决策**：所有数据以 JSON 文件形式存储在 NAS 文件系统，不使用任何数据库（SQLite、PostgreSQL 等）。

**背景**：
- 公司 NAS 是现有基础设施，已有访问权限
- 数据库需要额外部署和运维成本
- 数据集规模预期 < 100 万条，文件系统性能足够

**实现方式**：
- 每条数据 = `{id}.json`，存放在对应状态的子目录中
- 数据状态（raw/processed/.../checked）通过**目录位置**隐式表达
- `NASManager.update()` 会先删旧文件，再在新状态目录写入（"目录即状态机"）

**权衡**：
- ✅ 零额外依赖，透明可读，方便调试
- ✅ 天然支持增量备份（rsync 即可）
- ❌ 大数据量下查询性能较低（每次列表需扫描目录）
- ❌ 无事务，并发写入有冲突风险（当前单进程，可接受）

**未来扩展**：如需支持多进程或大规模数据，可替换 `storage/nas.py` 为 SQLite 实现，接口不变。

---

## ADR-002：数据状态机设计

**状态流转**：

```
raw → processed → pre_annotated → labeling → labeled → checked
                                                           ↓
                                                        export/
```

- `raw`：刚上传，未清洗
- `processed`：文本清洗完成
- `pre_annotated`：LLM 已预测标签（model_pred + model_score）
- `labeling`：某标注员已"取走"，标注中（防止多人重复标注同一条）
- `labeled`：人工标注完成（label + annotator + annotated_at）
- `checked`：通过冲突检测，高质量数据，可导出

**注意**：`conflict_flag=True` 的数据保留在 `labeled` 状态，等待人工复核后手动提升为 `checked`。

---

## ADR-003：Pipeline 引擎设计

**4 个步骤**：`process → pre_annotate → embed → check`

**设计原则**：
1. 每步操作**幂等**：重复运行不会破坏数据（已处理的数据跳过）
2. 步骤间**松耦合**：可单独运行任意步骤
3. 状态**持久化**：写入 `nas/pipeline_status.json`，重启后可查

**并发模式**：
- `POST /pipeline/run` → FastAPI `BackgroundTasks`，非阻塞
- `POST /pipeline/run-step` → 同步执行，适合调试

**进度追踪**：前端每 3 秒 poll `GET /pipeline/status`，显示进度条。

---

## ADR-004：冲突检测算法

**类型 1：标注冲突（Label Conflict）**

```python
# 同一文本 text 被不同 annotator 标注了不同 label
group_by(text) → find groups where len(unique labels) > 1
```

适用场景：多标注员同时标注同一批数据时。

**类型 2：语义冲突（Semantic Conflict）**

```python
# cosine_similarity(vec_A, vec_B) > threshold AND label_A != label_B
```

- 触发条件：相似度 > `config.similarity.threshold_high`（默认 0.9）
- 使用 FAISS 加速检索（退化为 numpy 暴力时 O(N²)）
- 含义：语义几乎相同的两条文本被标了不同的意图，说明标注不一致

**处理流程**：
- 冲突条目：`conflict_flag=True`，保留在 `labeled/`
- 人工在冲突检测页面逐条审核，点"通过"后移入 `checked/`
- 干净条目：直接升级为 `checked/`

---

## ADR-005：Embedding 模块设计（Mock 优先）

**两种模式**（`config.embedding.use_mock`）：

| 模式 | 实现 | 适用场景 |
|------|------|---------|
| `use_mock: true` | 基于 text hash 的确定性随机单位向量 | 开发/演示（无需 GPU） |
| `use_mock: false` | SentenceTransformer 本地加载 | 生产（需配置 model_path） |

**关键设计**：mock 模式下，相同文本总是生成相同向量（hash 种子），保证冲突检测结果的稳定性。

**切换方式**：改 `config.yaml`，在配置中心点"重载模型"，无需重启服务。

---

## ADR-006：LLM 预标注接口预留

`backend/modules/model.py` 中的 `_call_real_llm()` 是唯一需要替换的函数：

```python
async def _call_real_llm(text: str, labels: list[str]) -> tuple[str, float]:
    # 修改此处接入内部 LLM 平台
    payload = { "model": settings.llm_model_name, "messages": [...] }
    resp = await httpx.AsyncClient().post(settings.llm_api_url, json=payload)
    # 解析返回值 ↓
    raw_label = resp.json()["choices"][0]["message"]["content"].strip()
```

接入新平台：只需修改 `payload` 结构和 `raw_label` 解析逻辑，接口签名不变。

---

## ADR-007：前端 8 个页面设计

| 路由 | 页面 | 核心功能 |
|------|------|---------|
| `/dashboard` | Dashboard | 统计卡片 + Bar Chart + Pipeline 状态 |
| `/data` | 数据管理 | 拖拽上传（xlsx/json/csv）+ 列表 + 状态过滤 |
| `/pre-annotation` | 预标注 | 触发 pre_annotate 步骤 + 结果列表 |
| `/annotation` | 标注 | 翻牌式（Next → 展示文本 → 点击标签即提交）|
| `/conflicts` | 冲突检测 | 运行 check + 分类展示冲突 + 逐条审核 |
| `/config` | 配置中心 | 全量参数表单编辑 + 保存 + 重载模型 |
| `/export` | 导出 | 选格式（JSON/Excel）→ 生成 → 下载历史 |
| `/login` | 登录 | JWT 表单登录 |

**状态管理**：@tanstack/react-query（无 Redux/Zustand，简单即可）。

**Auth 流程**：`localStorage` 存 token → axios interceptor 自动附加 → 401 跳 `/login`。

---

## ADR-008：配置中心设计（热更新）

- `GET /api/config` → 返回完整配置（密码字段用 `***` 脱敏）
- `POST /api/config/update` → 覆盖写入 `config.yaml` + `Settings.reload()`
- `Settings` 是单例，`update()` 直接修改内存 + 持久化，**无需重启**

例外：如果修改了 `embedding.model_path`，需要额外调用 `POST /api/config/reload-model`，因为模型是懒加载单例。

---

## 技术债务

| 项目 | 风险 | 建议 |
|------|------|------|
| 无并发写入保护 | labeled/ 目录多进程写冲突 | 加文件锁或迁移 SQLite |
| Pipeline 状态写 JSON | 重启时状态可能不准 | 问题不大，可接受 |
| 标注"取走"机制弱 | `labeling` 状态无超时回收 | 加定时任务清理超时 labeling 条目 |
| JWT secret 写死 config | 需妥善保管 config.yaml | ✅ 已通过 .gitignore 处理 |
