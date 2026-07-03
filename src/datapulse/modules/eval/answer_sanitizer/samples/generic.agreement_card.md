# 样例 · generic.agreement_card

**解析器**：`AgreementCardParser`（generic.py，所有 BU 通用）
**结构判据**：剥开嵌套数组后的 dict 含 `agreements` 非空数组
**提取**：`请阅读并同意以下协议：` + 各 `agreements[].title` 顿号连接

协议同意卡：首次使用/协议更新时弹出的协议列表，让用户勾选同意。
非对用户问题的回答，是流程性弹窗——输出标明需用户同意，供 Judge 判为未承接。

> 注：真实日志外层多套一层数组 `[[{...}]]`（双层），解析器用 `_first_dict`
> 逐层剥到第一个 dict，单层 `[{...}]` 也兼容。

## 原始答案

```json
[ [ {
  "agreements" : [ {
    "appTitleName" : "平安证券",
    "outer" : false,
    "id" : 17,
    "title" : "证券大模型协议",
    "type" : 4,
    "version" : "V1.0.0",
    "selected" : false,
    "url" : "https://superagent-prd.pingan.com.cn/mobile/html/zq-thl-model-privacy.html",
    "typeCode" : "llmProtocolTypeCode"
  } ],
  "isUpdate" : 0
} ] ]
```

## 期望解析结果

```
请阅读并同意以下协议：证券大模型协议
```
