# 样例 · securities.robot_menu

**解析器**：`RobotMenuItemsParser`（securities.py）
**结构判据**：`msgContext.template == "robotMenuItems"`
**提取**：`msgInfo.menuItems.header` + `msgInfo.menuItems.questions[]` 各一行
（注意 template 在 msgContext 顶层；msgContent 常是空串；header 与 questions 同在 menuItems 内）

证券·小安机器人反问菜单卡：机器人没直接答，而是列出几个候选问题让用户点选。
与 robot_text_answer 结构同套路（template 在 msgContext 顶层、内容挂 msgInfo），
区别是问题在 menuItems 而非 relatedQuestions。

## 原始答案

```json
[ {
  "roomMark" : "person",
  "msgType" : "aat_text",
  "msgContext" : "{\"template\":\"robotMenuItems\",\"msgId\":\"2bf2f52d-b5f7-4e9e-a3d5-2e0118b38ee1\",\"source\":\"ucprobot_wia\",\"msgInfo\":{\"msgContent\":\"\",\"menuItems\":{\"questions\":[\"交易股票有什么费用\",\"交易基金有什么费用\",\"交易债券有什么费用\"],\"header\":\"请问您是想咨询以下哪个问题：\"},\"button\":false,\"sub_type\":\"\",\"bot\":\"分类模型\",\"curr_model\":\"semantics_model\"}}",
  "msgId" : "2bf2f52d-b5f7-4e9e-a3d5-2e0118b38ee1",
  "sessionId" : "000e1c0410774ba2b3bbe922eedf3d5c",
  "groupCode" : "ZQ_THS_09",
  "msgDate" : 1781753566278
} ]
```

## 期望解析结果

```
请问您是想咨询以下哪个问题：
交易股票有什么费用
交易基金有什么费用
交易债券有什么费用
```
