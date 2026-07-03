# 样例 · securities.xiaoan_card

**解析器**：`XiaoAnCardParser`（securities.py）
**结构判据**：`msgContext.msgInfo` 存在（小安机器人渲染卡的统一入口）
**提取**：按已知字段路径逐个兜底 —— msgContent（最常见）/ data.context / 同花顺 thsData / 列表卡片 list

证券·小安机器人的普通答案卡，含多种变体（下面各给一个原文）。

## 变体 1：msgInfo.msgContent（最常见）

```json
[ { "msgContext": "{\"msgInfo\":{\"msgContent\":\"<p>您的持仓查询结果如上。</p>\"}}" } ]
```
期望：`您的持仓查询结果如上。`

## 变体 2：同花顺智能选股 thsData

```json
[ { "msgContext": "{\"msgInfo\":{\"data\":{\"thsData\":{\"answer\":[{\"txt\":[{\"content\":\"{\\\"components\\\":[{\\\"data\\\":{\\\"content\\\":\\\"<p>主力净流入前三：A/B/C</p>\\\"}}]}\"}]}]}}}}" } ]
```
期望：`主力净流入前三：A/B/C`

## 变体 3：列表卡片 msgInfo.data.list[].data.content

```json
[ { "msgContext": "{\"msgInfo\":{\"data\":{\"list\":[{\"data\":{\"content\":\"<p>开户营业部：深圳分公司</p>\"}}]}}}" } ]
```
期望：`开户营业部：深圳分公司`
