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
    advice_card_system.md      优化建议·多专项建议共用系统人设
    advice_dispatch_global.md  优化建议·分发诊断(全局)
    advice_resolved_global.md  优化建议·解决率诊断(全局)
    advice_new_business.md     优化建议·新业务分类发现
    advice_intent_dispatch.md  优化建议·分类分发提升(逐分类,占位 {intent_name})
    advice_intent_resolved.md  优化建议·分类解决率提升(逐分类,占位 {intent_name})
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

### 二、优化建议(整批评测后,多专项各调一次)

一个维度一张卡:固定 3(全局分发/全局解决率/新分类)+ 动态 2N(每业务分类·分发/解决率),
各调一次 LLM、各出一段纯文本 markdown。料由 `advice_facts.build_facts` 从落盘 rows 重聚合,
`advisor.build_card_prompts` 按 token 预算填模板组 prompt(尽量喂满上下文窗口)。

| 文件 | 作用 | 可用占位符 |
|------|------|-----------|
| `advice_card_system.md` | 多专项建议共用的顾问人设 | `{bu_name}` |
| `advice_dispatch_global.md` | 全局分发诊断(漏收/误收) | `{payload}` |
| `advice_resolved_global.md` | 全局解决率诊断(四归因分布) | `{payload}` |
| `advice_new_business.md` | 新业务分类发现(非本 BU 问题) | `{payload}` |
| `advice_intent_dispatch.md` | 逐分类·分发提升 | `{payload}`、`{intent_name}` |
| `advice_intent_resolved.md` | 逐分类·解决率提升 | `{payload}`、`{intent_name}` |

> 模型输出为纯文本 markdown(非结构化)。返回结构 `{source, cards:[{id, title, dimension, category, text}]}`。

## 注意

- 占位符用 `{xxx}`,代码用字符串替换填充(非 Python format),模板里写 JSON 花括号不冲突。
- 改完文件需**重启后端**(内容做了 LRU 缓存)。
- 无模型时的规则版兜底建议在 `advisor.rule_based_cards`,是代码逻辑渲染成同构文本卡,不是提示词。
