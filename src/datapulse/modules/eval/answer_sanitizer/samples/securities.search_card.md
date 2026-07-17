# 样例 · securities.search_card

**解析器**：`SearchCardParser`（securities.py，证券专属）
**结构判据**：剥开嵌套数组后的 dict 含 `searchData` 且 `searchData` 内含 `searchType`
**提取**：固定文案 `搜索返回`

搜索返回卡：证券日志里大量出现的一种答案——系统没有直接回答某个具体业务问题，
而是把用户导向搜索 / 快捷服务入口（诊股/选股/查行情等）。用户搜索条件五花八门
（科创ETF / 某股票 / 某基金 / 某ETF…），`query` 各不相同，但本质都是同一种「返回
搜索入口」的处理，故净化成统一文案 `搜索返回`。

配合短路规则使用：触发问题配 `*`（任意问题）、期望答案配 `搜索返回`、业务分类
配「通用分类」、answer_resolved 配 `yes`，即把这类答案统一判为「搜索返回，默认为解决」，
免调大模型。真实日志外层多套一层数组，用 `first_dict` 剥。

## 原始答案

```json
[ {
  "searchData" : {
    "searchType" : 2,
    "query" : "科创ETF",
    "agentName" : "问诊股",
    "title" : "问诊股",
    "btnInfo" : {
      "btnName" : "去查看",
      "actionType" : 1
    },
    "desc" : "诊股/基、选股/基、查行情等，请到快捷服务"
  }
} ]
```

## 期望解析结果

```
搜索返回
```
