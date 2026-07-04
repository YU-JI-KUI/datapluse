# 样例 · life.service_flow_card

**解析器**：`LifeServiceFlowCardParser`（life_insurance.py，寿险专属 bu_codes=("life",)）
**结构判据**：`gbdData.oneKeyServiceName`（兜底 `agentName`）存在，`card_content` 无 data 节点
**提取**：`为您转接【服务名】服务`

寿险金管家服务流程卡（一键办理）：把用户导向某业务办理流程，无文本正文，
只有服务名（如「客户信息变更」）。归一为「为您转接【服务名】服务」，让 Judge 识别为已承接。

## 原始答案

```json
[ [ {
  "code" : "00",
  "source_bu_type" : "C027Flow",
  "gbdData" : {
    "answerType" : "其他",
    "oneKeyServiceName" : "客户信息变更",
    "agentName" : "客户信息变更"
  },
  "service_type" : "life_insurance",
  "card_content" : {
    "expParam" : "{\"sceneClass\":\"COMMON_SINGLE\",\"subSceneClass\":\"CUSTOMER_CARD\"}",
    "type" : "C027Flow",
    "status" : "02"
  },
  "bu_type" : "shouxian",
  "timestamp" : "2026-06-30T01:13:24Z"
} ] ]
```

## 期望解析结果

```
为您转接【客户信息变更】服务
```
