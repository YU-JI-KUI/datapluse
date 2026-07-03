# 样例 · generic.jump_platform

**解析器**：`JumpPlatformParser`（generic.py，所有 BU 通用）
**结构判据**：剥开嵌套数组后的 dict 含 `crossCardType == "JUMPPLATFORM"`
**提取**：固定话术 `本 BU 不承接，请使用【title】，desc`

跳端卡：本 BU 拒识后返回的跨 App 跳转卡。如寿险金管家里问题被拒识，
直接给出跳转到平安乐健康的链接卡，标题/描述指向目标 App。
注意它也带 `appType`，priority 必须小于 LlmApiResp，否则被当 LLM 响应取空 msg。
真实日志外层可能多套一层数组（单层 `[{...}]` 与双层 `[[{...}]]` 都兼容，用 `first_dict` 剥）。

## 原始答案

```json
[ {
  "bizCd" : "Rel5OlwgEq9QAp1ap51FJaXq4TiGmr3EZLaZ2yiCMIaE9yWSYLLe3pqn1G9vqcTYTgw5d/qSKXiDaoHC+gTocBZdBqLenOVS3KSO0j/A1nM=",
  "crossCardType" : "JUMPPLATFORM",
  "appType" : "jkbx",
  "downloadUrl" : "https://mcore.health.pingan.com/deeplink/index.html?sCode=homePage",
  "icon" : "jkxIcon",
  "packageName" : "com.pa.health",
  "is_jump" : "1",
  "title" : "平安乐健康",
  "btn" : "去使用",
  "url" : "pahealth://padeepsealink?linkid=DSLINK000005491",
  "desc" : "平安乐健康为您提供更完整的服务"
} ]
```

## 期望解析结果

```
本 BU 不承接，请使用【平安乐健康】，平安乐健康为您提供更完整的服务
```
