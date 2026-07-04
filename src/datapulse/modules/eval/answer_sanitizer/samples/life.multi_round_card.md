# 样例 · life.multi_round_card

**解析器**：`LifeMultiRoundCardParser`（life_insurance.py，寿险专属 bu_codes=("life",)）
**结构判据**：`card_content.data.answer` 与 `card_content.data.capsule` 同时存在（intentCode=COMMON_MULTIPLE，区别于澄清卡的 msg + options、FAQ 卡的 faqID）
**提取**：`data.answer` 正文 + 各胶囊 `data.capsule[].label` 逐行

寿险金管家多轮文本卡：给出正文后用胶囊引导用户下一轮追问（gbdData.answerType=多轮）。
正文在 answer，追问选项在 capsule[].label（不是 options[].name）。输出正文一行 + 每个胶囊 label 一行。

## 原始答案（节选，capsule 保留 2 项）

```json
[ [ {
  "code" : "00",
  "source_bu_type" : "2003",
  "gbdData" : { "cardType" : "保险是转移风险...", "answerType" : "多轮" },
  "service_type" : "life_insurance",
  "card_content" : {
    "data" : {
      "capsule" : [
        { "label" : "急需资金" },
        { "label" : "退保办理流程" }
      ],
      "extendParam" : { "round" : 1, "intentCode" : "COMMON_MULTIPLE", "query" : "退保" },
      "answer" : "保险是转移风险、降低经济损失的一种手段，建议您慎重考虑是否有必要退保。若需资金急用，建议您尝试一下方式了解：",
      "intentStoreName" : "退保"
    },
    "type" : "2003",
    "status" : "02"
  },
  "bu_type" : "shouxian",
  "timestamp" : "2026-06-30T01:13:15Z"
} ] ]
```

## 期望解析结果

```
保险是转移风险、降低经济损失的一种手段，建议您慎重考虑是否有必要退保。若需资金急用，建议您尝试一下方式了解：
急需资金
退保办理流程
```
