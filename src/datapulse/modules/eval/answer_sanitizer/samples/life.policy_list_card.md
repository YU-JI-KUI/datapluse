# 样例 · life.policy_list_card

**解析器**：`LifePolicyListCardParser`（life_insurance.py，寿险专属 bu_codes=("life",)）
**结构判据**：顶层 `[[{...}]]`，`card_content.data.policyInfos` 为非空数组（区别于 FAQ 卡的 faqID）
**提取**：抬头 `card_content.data.text` + 每份保单一行（`planName` 险种名 + `appDate` 投保日）

寿险金管家保单列表卡：查保单后返回名下保单清单。
保单号 polNo 是长数字串，对 Judge 判定无益，不进正文。

## 原始答案（节选，policyInfos 保留 2 份）

```json
[ [ {
  "code" : "00",
  "source_bu_type" : "policyList",
  "gbdData" : { "answerType" : "其他" },
  "service_type" : "life_insurance",
  "card_content" : {
    "data" : {
      "sceneType" : "policyNotFound",
      "text" : "帮您找到6份保单",
      "policyInfos" : [ {
        "polNo" : "10217006601204098209",
        "clientName" : "皮*",
        "planName" : "平安江泰境内出行旅意险(互联网Plus版)",
        "appDate" : "2026-05-30"
      }, {
        "polNo" : "P180000032501673",
        "clientName" : "皮*",
        "planName" : "鑫福星",
        "appDate" : "2021-06-29"
      } ]
    },
    "type" : "policyList",
    "status" : "02"
  },
  "bu_type" : "shouxian",
  "timestamp" : "2026-06-30T01:13:28Z"
} ] ]
```

## 期望解析结果

```
帮您找到6份保单
平安江泰境内出行旅意险(互联网Plus版) 2026-05-30
机动车辆商业保险(2020版) 2023-11-29
机动车交通事故责任强制保险(2020版) 2023-11-29
机动车辆商业保险(2020版) 2022-11-29
机动车交通事故责任强制保险(2020版) 2022-11-29
鑫福星 2021-06-29
```
