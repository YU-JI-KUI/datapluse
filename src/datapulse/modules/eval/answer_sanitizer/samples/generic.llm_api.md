# 样例 · generic.llm_api

**解析器**：`LlmApiRespParser`（generic.py，所有 BU 通用）
**结构判据**：顶层首元素 dict 含 `appType`
**提取**：`msg` 或 `standardQuestion` 去 HTML 后的纯文本

跨 BU 通用的 LLM API 响应结构。

## 原始答案

```json
[ { "appType": "qa", "msg": "缴费成功，<span>感谢</span>。" } ]
```

## 期望解析结果

```
缴费成功，感谢。
```
