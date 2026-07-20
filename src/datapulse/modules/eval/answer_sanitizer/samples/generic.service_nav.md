# 样例 · generic.service_nav

**解析器**：`ServiceNavCardParser`（generic.py，所有 BU 通用）
**结构判据**：顶层首元素含非空 `tabs` 数组，且至少一个 tab 有 `funcList`
**提取**：`title` + `subTitle`（去 HTML）逐行

服务导航卡：如「平安救急服务」导航页，含卖点 pointList + 分 tab 的功能菜单。
只取标题 + 副标题概括，功能菜单跨 tab 大量重复、对判定无益，不进正文。

## 原始答案（节选，tabs/funcList 各留少量）

```json
[ [ {
  "summary" : "",
  "pointList" : [
    { "summary" : "覆盖救急领域", "title" : "<span class=\"num\">3</span><span class=\"text\">大领域</span>", "order" : 0 }
  ],
  "subTitle" : "7X24小时全天候紧急救援服务",
  "success" : 0,
  "tabs" : [ {
    "name" : "推荐",
    "order" : 0,
    "funcList" : [
      { "name" : "SOS", "iconurl" : "sos", "order" : 0 },
      { "name" : "银行卡挂失", "iconurl" : "lossReportBankCard", "order" : 1 }
    ]
  } ],
  "title" : "平安救急服务",
  "jumpUrl" : ""
} ] ]
```

## 期望解析结果

```
平安救急服务 7X24小时全天候紧急救援服务
```
