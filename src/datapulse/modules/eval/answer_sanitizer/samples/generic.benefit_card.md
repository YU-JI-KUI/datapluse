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

## 寿险样例（同一解析器覆盖）

寿险活动权益卡 `catalogId=activity-mx-benefit-card`，结构与证券权益卡一致，命中同一通用解析器，无需新增寿险专属子类。

### 原始答案

```json
[ {
  "activityId" : "102",
  "activityName" : "615活动",
  "activityType" : "3",
  "catalogId" : "activity-mx-benefit-card",
  "data" : {
    "benefits" : [ {
      "benefitIcon" : "mx-equity-sx-coin",
      "expireTime" : "2026-05-16 23:59:59",
      "benefitName" : "打卡领金币",
      "benefitSubTitle" : "随心兑好物",
      "buttonInfo" : { "buttonName" : "去打卡", "buttonType" : "link", "buttonLink" : "pars://...", "buttonQuery" : "" },
      "benefitStatus" : 1
    }, {
      "benefitIcon" : "mx-equity-sx-lift",
      "expireTime" : "2026-05-16 23:59:59",
      "benefitName" : "周二金喜日",
      "benefitSubTitle" : "好礼抽不停",
      "buttonInfo" : { "buttonName" : "去抽奖", "buttonType" : "link", "buttonLink" : "pars://...", "buttonQuery" : "" },
      "benefitStatus" : 1
    } ],
    "cardType" : "multi",
    "cardHead" : { "artistAvatar" : "https://...", "subTitle" : "多重福利速来领取", "mainTitle" : "恭喜获得专属礼遇" },
    "canCollect" : "1",
    "activityInfo" : { "subTitle" : "限时福利，先到先得", "mainTitle" : "恭喜获得专属礼遇" },
    "disclaimer" : "温馨提示：本次领好礼活动内容及活动礼品由平安人寿保险股份有限公司设计提供，与艺人无任何关联。"
  },
  "event" : "beginRendering",
  "isFirstClaim" : "1",
  "surfaceId" : "8c61b5a7-9b7c-4be5-976d-0bda3e00f460",
  "version" : "1.0.0"
} ]
```

### 期望解析结果

```
恭喜获得专属礼遇
打卡领金币
周二金喜日
```
