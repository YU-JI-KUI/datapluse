# 评测聚合指标(按业务分类切片)

{payload}

# 任务

请找出最需要优化的 **3-5 个点**,每个点给出以下字段:

| 字段 | 含义 |
| --- | --- |
| `scope` | 作用域(具体业务分类 / 全局) |
| `severity` | 严重度:`high` / `medium` / `low` |
| `problem` | 一句话问题 |
| `root_cause` | 根因:`分发问题` / `答案问题` / `数据问题` / `需人工` 之一 |
| `suggestion` | 具体可落地的优化动作(如:补该业务分类标问、调分发阈值、补知识库、转人工兜底) |
| `evidence` | 支撑数字 |

# 输出要求

只输出 JSON 数组,形如:

```json
[{"scope":"...","severity":"high","problem":"...","root_cause":"...","suggestion":"...","evidence":"..."}]
```
