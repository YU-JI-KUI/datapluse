# 提示词统一管理

所有给大模型的上下文(人设、判定规则、业务分类、优化建议)都在本目录,**代码里不写死任何提示词文本**。改提示词只改这里的文件,重启后端即生效(文件内容有缓存)。

提示词正文用 `.md`(Qwen 系列对 markdown 结构更易理解);业务分类数据用 `.json`(结构化,前端还要用它计数/列名)。

加载入口:`app/core/eval/prompt_loader.py`
- `load_prompt(name)` —— 读本目录根下的共用模板。
- `load_bu_prompt(bu_code, name)` —— **优先 `<bu_code>/<name>`,缺则回退 `_default/<name>`**。

## 目录结构

```
prompts/
  judge_user.md           ← Judge 共用骨架(对话数据排版 + 任务/输出占位),所有 BU 一套
  _default/               ← 通用提示词(BU 没单独写时回退用)
    judge_system.md         Judge 系统人设
    task_dispatch.md        维度1:该不该本BU承接
    task_business_type.md   维度2:业务分类打标
    task_resolved.md        维度3:是否解决
    task_review.md          维度4:是否需人工复核
    advice_system.md        优化建议·系统人设
    advice_user.md          优化建议·任务与输出格式
  securities/             ← 证券专属(只放和通用不同的文件)
    judge_system.md         证券人设
    task_dispatch.md        证券承接 SOP
    categories.json         证券业务分类定义(必有)
  life/
    judge_system.md
    categories.json         寿险业务分类定义(必有)
```

> `categories.json` 是每个 BU **必有**的(业务分类不能回退到通用)。其余文件可选,缺则回退 `_default/`。

## 怎么给某个 BU 写专属规则

在 `<bu_code>/` 下放一个**同名文件**即可覆盖通用版;没放的自动用 `_default/`。
例:给证券写专属"是否解决"规则 → 新建 `securities/task_resolved.md`。
加新 BU → 建 `<新bu_code>/` 目录,放它的 `categories.json` + 任何要专属的 `.md`。

> `bu_code`:证券=`securities`、寿险=`life`,见 `app/core/bu/registry.py`。

## 业务分类数据(categories.json)

结构:`{"categories": {"分类名": {"definition": "定义(可含正例/反例)"}}}`

- 喂给模型时由 `BUConfig.intents_block()` 渲染成 **markdown 表格**(`| 业务分类 | 定义 |`),Qwen 更易理解。
- 前端 BU 选择器用它计数(`intent_count`)、列分类名。
- **所以保持 JSON 结构**,不要改成纯表格文本——否则前端要解析 markdown,分类名含特殊字符会出错。

## 两套提示词分别需要哪些数据(占位符)

### 一、Judge 评测(每条对话一次)

| 文件 | 作用 | 可用占位符 |
|------|------|-----------|
| `judge_user.md` | 对话数据骨架 + 任务/输出装配 | `{intents}` 业务分类表格(来自 `<bu>/categories.json`)、`{question}` 客户问题、`{ctx}` 多轮上下文(会话重组,含前文AI答)、`{answer_text}` AI答案原文、`{next_user_turn}` 下一轮问题(仅评解决度用)、`{dispatched_flag}` 日志是否已分给本BU、`{tasks}` 四个维度规则拼接、`{output_schema}` 输出字段契约 |
| `judge_system.md` | 系统人设 | 无占位符,纯文本 |
| `task_*.md` | 四个评测维度的判定规则 | 无占位符,纯规则文本,被 `{tasks}` 按顺序拼接 |

### 二、优化建议(整批评测后一次)

| 文件 | 作用 | 可用占位符 | 数据来源 |
|------|------|-----------|---------|
| `advice_system.md` | 优化顾问人设 | `{bu_name}` BU 展示名 | `bu.name` |
| `advice_user.md` | 任务说明 + 输出格式 | `{payload}` 聚合指标 JSON | `compute_insights()` + BU 分发漏斗统计 |

`{payload}` 喂给模型的内容(`advisor.build_advice_prompt` 组装):
- **BU分发**:准确率 + 两类错误(漏收 该分未分 / 误收 该拒未拒)
- **整体端到端解决率**
- **各业务分类切片**(仅样本量≥3):分类名、进漏斗样本量、端到端解决率、需复核率、未解决典型问题

> 模型返回的建议数组结构:`scope / severity / problem / root_cause / suggestion / evidence`。

## 注意

- 占位符用 `{xxx}`,代码用字符串替换填充(非 Python format),模板里写 JSON 花括号不冲突。
- 改完文件需**重启后端**(内容做了 LRU 缓存)。
- 模型提示词只有两套(Judge + 优化建议),没有第三处。无模型时的规则版兜底建议在 `advisor.rule_based_advice`,是代码阈值逻辑,不是提示词。
