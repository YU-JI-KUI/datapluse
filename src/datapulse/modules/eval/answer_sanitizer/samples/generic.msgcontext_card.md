# 样例 · generic.msgcontext_card

**解析器**：`MsgContextCardParser`（generic.py，所有 BU 通用）
**结构判据**：顶层首元素 dict 含 `msgContext`，其 `msgInfo` 存在
**提取**：`msgInfo.msgContent`（纯文本）/ `data.content` / `data.context.data.content`

渲染卡的通用主体结构，寿险（金管家）与证券（小安）日志里都是**绝对主体**
（真实样本各数千条 100% 命中）。证券特有的 thsData 同花顺、list 列表卡片由
证券专属 XiaoAnCardParser 处理（专属先于通用）。

> 注：早期此逻辑锁在证券专属解析器里，且只认 `data.context.data.content`，
> 导致最常见的 `data.content` 直挂结构全部漏网、寿险 100% 净化失效。
> 现拆为通用解析器并补 `data.content` 路径。

## 原始答案

```json
[ {
  "roomMark" : "person",
  "msgType" : "aat_text",
  "msgContext" : "{\"msgInfo\": {\"data\": {\"content\": \"<p>针对『我的自选股今天表现如何』,已为您查询并处理完成,结果如上。</p>\"}}}"
} ]
```

## 期望解析结果

```
针对『我的自选股今天表现如何』,已为您查询并处理完成,结果如上。
```
