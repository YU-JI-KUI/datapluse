# 样例 · life.clarify_card

**解析器**：`LifeClarifyCardParser`（life_insurance.py，寿险专属 bu_codes=("life",)）
**结构判据**：`card_content.data.msg` 存在（labelId=llm_recommend，无 faqID，区别于 FAQ 卡）
**提取**：`data.msg` 澄清话术 + 各推荐问题 `data.options[].name` 逐行

寿险金管家意图不明澄清卡：LLM 兜底反问（gbdData.answerType=意图不明），
给出澄清话术 + 推荐问题让用户选。输出话术一行 + 每个推荐问题一行。

## 原始答案（节选，options 保留 2 项）

```json
[ [ {
  "code" : "00",
  "source_bu_type" : "200",
  "gbdData" : { "answerType" : "意图不明" },
  "service_type" : "life_insurance",
  "card_content" : {
    "data" : {
      "msg" : "您好，我需要更多的信息来理解您的问题，可以再详细描述一下您的问题，我会尽力解答。",
      "labelId" : "llm_recommend",
      "options" : [
        { "msg" : "臻享家医服务在哪里", "name" : "臻享家医服务在哪里" },
        { "msg" : "想获取臻享家医服务如何操作", "name" : "想获取臻享家医服务如何操作" }
      ],
      "historyNoDisable" : true
    },
    "type" : "200",
    "status" : "02"
  },
  "bu_type" : "shouxian",
  "timestamp" : "2026-06-30T01:13:24Z"
} ] ]
```

## 期望解析结果

```
您好，我需要更多的信息来理解您的问题，可以再详细描述一下您的问题，我会尽力解答。
臻享家医服务在哪里
想获取臻享家医服务如何操作
臻享家医如何开通
臻享run入口
平安臻享run打不开
```
