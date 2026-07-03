# 样例 · securities.xiaoan_card

**解析器**：`XiaoAnCardParser`（securities.py，证券专属）
**结构判据**：`msgContext.msgInfo.data` 下有 `thsData` 或 `list`
**提取**：同花顺 thsData / 列表卡片 list

证券·小安机器人**特有**的两种渲染卡。基础的 msgContent/data.content 由通用
`MsgContextCardParser` 处理，这里只认证券日志特有结构（专属先于通用，先命中）。

## 变体 1：同花顺智能选股 thsData

```json
[ { "msgContext": "{\"msgInfo\":{\"data\":{\"thsData\":{\"answer\":[{\"txt\":[{\"content\":\"{\\\"components\\\":[{\\\"data\\\":{\\\"content\\\":\\\"<p>主力净流入前三：A/B/C</p>\\\"}}]}\"}]}]}}}}" } ]
```
期望：`主力净流入前三：A/B/C`

## 变体 2：列表卡片 msgInfo.data.list[].data.content

```json
[ { "msgContext": "{\"msgInfo\":{\"data\":{\"list\":[{\"data\":{\"content\":\"<p>开户营业部：深圳分公司</p>\"}}]}}}" } ]
```
期望：`开户营业部：深圳分公司`
