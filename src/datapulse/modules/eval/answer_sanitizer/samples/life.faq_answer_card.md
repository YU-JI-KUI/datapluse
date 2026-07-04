# 样例 · life.faq_answer_card

**解析器**：`LifeFaqAnswerCardParser`（life_insurance.py，寿险专属 bu_codes=("life",)）
**结构判据**：`card_content.data.answerList` 为非空数组且 `data.rankType="FAQ"`（区别于 FAQ 知识库卡的 faqID、多轮卡的 answer+capsule）
**提取**：`data.answer`（多段 `<p>` HTML）按块级标签 `</p>/<br>/</div>/</li>` 拆行，去 HTML 得纯文本

寿险金管家 FAQ 答案卡（H5 访客渠道 source=H5_SAVisitor）：命中知识库后直接返回 HTML 正文，
正文含多段落 + 超链接（门店预约等）。去标签后按段落逐行输出，链接文字保留、URL 丢弃。

## 原始答案（节选，answerList 保留 1 项）

```json
[ [ {
  "code" : "00",
  "source_bu_type" : "faq",
  "gbdData" : { "answerType" : "其他" },
  "service_type" : "life_insurance",
  "card_content" : {
    "data" : {
      "matchQuestion" : "深圳门店",
      "rankType" : "FAQ",
      "answerList" : [ {
        "matchQuestion" : "深圳门店",
        "rankType" : "FAQ",
        "display" : "<p>您好，如需了解平安人寿的门店地址...</p>",
        "faqId" : 25941148,
        "stdQuestion" : "寿险公司门店信息查询"
      } ],
      "score" : 0.46984345,
      "stdQuestion" : "寿险公司门店信息查询",
      "answer" : "<p>您好，如需了解平安人寿的门店地址、时间等详细信息，可点击【<a href=\"https://m.lifeapp.pingan.com.cn/m/pss-v2/web/index.html#/reservationService/index?source=06\">门店预约</a>】选择所在城市自助查询；</p><p>温馨提醒：临柜前请提前预约，减少排队时间”</p><p><span>平安寿险门店电话</span></p>",
      "faqId" : 25941148,
      "subClassType" : 404
    },
    "type" : "faq",
    "status" : "02"
  },
  "bu_type" : "shouxian",
  "timestamp" : "2026-06-30T01:13:08Z"
} ] ]
```

## 期望解析结果

```
您好，如需了解平安人寿的门店地址、时间等详细信息，可点击【门店预约】选择所在城市自助查询；
温馨提醒：临柜前请提前预约，减少排队时间”
平安寿险门店电话
```
