# 样例 · generic.content_data

**解析器**：`ContentDataParser`（generic.py，所有 BU 通用）
**结构判据**：顶层 list → `first[0].content_data` 存在
**提取**：`content_data` 去 HTML 后的纯文本

跨 BU 通用的文本回复结构（寿险等 BU 也可命中）。

## 原始答案

```json
[ [ { "content_data": "您的保单已生效。" } ] ]
```

## 期望解析结果

```
您的保单已生效。
```

## 转人工样例（同一解析器覆盖）

content_data 为 `jgj_` 前缀（金管家转人工工单号）时，归一为「金管家转人工」，命中同一解析器。

### 原始答案

```json
[ [ {
  "zrg_reason" : "1",
  "content_type" : "text",
  "reply_role" : "jgj",
  "content_data" : "jgj_313201396405904666",
  "zrg_flag" : true
} ] ]
```

### 期望解析结果

```
金管家转人工
```
