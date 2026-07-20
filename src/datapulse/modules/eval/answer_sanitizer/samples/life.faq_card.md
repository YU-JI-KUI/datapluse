# 样例 · life.faq_card

**解析器**：`LifeFaqCardParser`（life_insurance.py，寿险专属 bu_codes=("life",)）
**结构判据**：顶层 `[[{...}]]`，`card_content.data.faqID` 存在（金管家 askBOB 知识库卡）
**提取**：正文（`gbdData.content`，兜底 `card_content.data.detail[0].content`）+ 各关联问题 `card_content.data.options[].name` 逐行

寿险金管家 FAQ 知识库卡：命中知识库后返回正文答案 + 关联推荐问题。
正文和 options 并存，输出正文一行 + 每个关联问题一行，让 Judge 看到完整承接内容。

## 原始答案（节选，options 保留 2 项）

```json
[ [ {
  "code" : "00",
  "gbdData" : {
    "standardQuestion" : "臻享家医服务入口",
    "cardType" : "臻享家医服务在哪里",
    "answerType" : "faq",
    "content" : "您好，臻享家医金管家服务路径：　（1）金管家首页－臻享RUN icon入口－平安家医（尊享版）　（2）金管家首页－我的－我的权益－臻享RUN－平安家医（尊享版）。"
  },
  "service_type" : "life_insurance",
  "card_content" : {
    "data" : {
      "kbId" : "3119",
      "answerFrom" : "faq",
      "queryQuestion" : "臻享家医服务在哪里",
      "options" : [
        { "msg" : "在哪里使用VIP家庭单", "name" : "在哪里使用VIP家庭单" },
        { "msg" : "金管家VIP服务模块路径", "name" : "金管家VIP服务模块路径" }
      ],
      "faqID" : "INSUR_FAQ",
      "detail" : [ { "content" : "您好，臻享家医金管家服务路径：……" } ]
    },
    "type" : "214",
    "status" : "02"
  },
  "bu_type" : "shouxian",
  "timestamp" : "2026-06-30T01:13:29Z"
} ] ]
```

## 期望解析结果

```
您好，臻享家医金管家服务路径：　（1）金管家首页－臻享RUN icon入口－平安家医（尊享版）　（2）金管家首页－我的－我的权益－臻享RUN－平安家医（尊享版）。 在哪里使用VIP家庭单 金管家VIP服务模块路径 VIP深圳专享商品服务在金管家哪里申请 VIP的机场接送服务在哪里申请 在哪儿申请VIP留学服务
```
