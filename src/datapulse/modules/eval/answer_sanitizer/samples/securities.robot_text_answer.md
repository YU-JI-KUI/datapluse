# 样例 · securities.robot_text_answer

**解析器**：`RobotTextAnswerParser`（securities.py）
**结构判据**：`msgContext.template == "robotTextAnswer"`
**提取**：`msgInfo.relatedQuestions.header` + `relatedQuestions.questions[]` 各一行
（注意 relatedQuestions 直接挂 msgInfo 下，无 msgContent 层；template 在 msgContext 外层）

证券·小安机器人关联问卡：没直接答，列出关联问题让用户确认咨询意图。
与 robot_menu 的区别：template 位置在 msgContext 外层、问题在 relatedQuestions 而非 menuItems。

## 原始答案

```json
[ {
  "roomMark" : "person",
  "msgType" : "aat_text",
  "msgContext" : "{\"template\":\"robotTextAnswer\",\"msgId\":\"afdc0771-ed6f-4ec3-82e7-372731fda015\",\"source\":\"ucprobot_wia\",\"msgInfo\":{\"relatedQuestions\":{\"footer\":\"\",\"questions\":[\"什么是当日委托\",\"撤单的介绍\",\"受理成功的订单介绍\"],\"header\":\"您咨询的是否为以下问题：\"}}}",
  "msgId" : "afdc0771-ed6f-4ec3-82e7-372731fda015",
  "sessionId" : "04edfaa2460e4f9ca3353b15c3314806",
  "groupCode" : "ZQ_THS_09",
  "msgDate" : 1780278785986
} ]
```

## 期望解析结果

```
您咨询的是否为以下问题：
什么是当日委托
撤单的介绍
受理成功的订单介绍
```
