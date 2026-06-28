"""寿险 BU 领域知识。

业务分类(原意图)清单维护在 `prompts/life/categories.json`,内网调整分类只改 JSON。
本意图体系为按寿险常见业务设计的合理占位,拿到真实分类文档后改 JSON 即可。
"""
from __future__ import annotations

from datapulse.modules.eval.bu.base import BUConfig

# intents 不在 import 期固化，由 registry.get_bu() 按当前库/文件动态注入（见 securities.py 说明）。
_INTENTS: dict = {}

# Mock 规则桩:关键词→意图(顺序敏感,先具体后宽泛)
_MOCK_RULES = [
    (["手机充值", "话费", "股票", "基金"], "拒识"),
    (["人工", "客服", "转人工", "客服电话"], "咨询客服"),
    (["理赔", "出险", "住院", "报销", "赔付"], "理赔咨询"),
    (["缴费", "续期", "扣款", "保费", "交钱"], "缴费续期"),
    (["保单", "保额", "受益人", "生效", "有效"], "保单查询"),
    (["变更", "退保", "复效", "改地址", "改电话", "保全"], "保全变更"),
    (["投保", "健康告知", "能买", "投保条件"], "投保咨询"),
    (["产品", "条款", "责任", "保什么", "对比"], "产品咨询"),
    (["万能", "账户价值", "结算利率", "追加", "领取"], "万能账户"),
    (["贷款", "保单贷", "借款", "贷多少"], "贷款咨询"),
    (["积分", "权益", "活动", "会员"], "活动"),
]

# 承接模块 -> 该模块负责的意图(mock 宽松分发匹配)
_MODULE_MAP = {
    "保单助手": ["保单查询", "保全变更", "缴费续期"],
    "理赔助手": ["理赔咨询"],
    "智能顾问": ["投保咨询", "产品咨询", "万能账户", "贷款咨询"],
    "客服": ["咨询客服", "活动"],
}

LIFE = BUConfig(
    code="life",
    name="寿险",
    description="平安寿险 AI 对话/智能问答系统:覆盖保单服务、缴费理赔、销售咨询等业务。",
    # 日志「分发BU」列里代表寿险的取值。拿到真实日志后按实际值补充。
    dispatch_aliases=("寿险", "人寿"),
    intents=_INTENTS,
    mock_intent_rules=_MOCK_RULES,
    mock_module_map=_MODULE_MAP,
    sample_calib="life_dialog_calib.xlsx",
    sample_prod="life_dialog_prod.xlsx",
)
