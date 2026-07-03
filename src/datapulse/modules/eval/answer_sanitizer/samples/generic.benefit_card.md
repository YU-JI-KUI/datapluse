# 样例 · generic.benefit_card

**解析器**：`BenefitCardParser`（generic.py，所有 BU 通用）
**结构判据**：顶层首元素 dict 含 `catalogId` 且 `data.benefits` 为非空数组
**提取**：`data.cardHead.mainTitle` + 各 `benefits[].benefitName` 逐行

权益领取结果卡：领权益后返回的结果卡，标题 + 各权益名。

## 原始答案

```json
[ {
  "catalogId" : "mx-activity-result-multiple",
  "data" : {
    "cardHead" : { "mainTitle" : "恭喜领取以下权益", "subTitle" : "数量有限尽快领取" },
    "benefits" : [
      { "benefitName" : "超级Level-2", "buttonName" : "去使用" },
      { "benefitName" : "科学投顾体验券", "buttonName" : "去使用" }
    ]
  }
} ]
```

## 期望解析结果

```
恭喜领取以下权益
超级Level-2
科学投顾体验券
```
