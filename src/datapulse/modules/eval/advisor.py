"""优化建议生成器。

读「业务洞察聚合指标 + 典型失败样例」→ 让大模型给出针对性的优化建议。
无模型时退化为规则版建议(基于阈值),保证任何环境都有可用输出。

建议结构(每条):
  scope        : 作用域(业务分类 / 全局)
  severity     : high / medium / low
  problem      : 一句话问题描述
  root_cause   : 根因判断(分发问题 / 答案问题 / 数据问题 / 需人工)
  suggestion   : 具体优化动作
  evidence     : 支撑数字
"""
from __future__ import annotations

import json

from datapulse.modules.eval.bu.base import BUConfig

# 规则版阈值:解决率低于此判为需优化
_LOW_RESOLVED = 0.6
_LOW_DISPATCH = 0.7
_HIGH_REVIEW = 0.4
_MIN_SAMPLES = 3  # 样本太少不下结论


def build_advice_prompt(insights: dict, bu: BUConfig, bu_dispatch: dict | None = None) -> list[dict]:
    """构造给大模型的消息:把聚合指标 + 失败样例填进外置模板。

    提示词在 prompts/_default/advice_system.md、advice_user.md(可被 prompts/<bu>/ 重写)。
    数据准备(payload)在代码里,模板只负责措辞与输出格式。
    占位符:advice_system 用 {bu_name};advice_user 用 {payload}(下方聚合指标 JSON)。
    """
    overall = insights["overall"]
    # 只把信息量大的切片喂给模型(进漏斗样本量足够的),控制 token
    slices = [s for s in insights["by_intent"] if s.get("in_bu_count", 0) >= _MIN_SAMPLES]
    payload = {
        "BU分发": bu_dispatch or {},   # 准确率 + 两类错误(漏收/误收)
        "整体问题解决率": overall["resolved_rate"],
        "各业务类型切片(问题解决率,分母=分发到本BU的子集)": [
            {
                "业务类型": s["name"],
                "进漏斗样本量": s.get("in_bu_count", 0),
                "问题解决率": s["resolved_rate"],
                "需复核率": s["needs_review_rate"],
                "未解决典型问题": s["unresolved_examples"],
            }
            for s in slices
        ],
    }
    system = bu.prompt("advice_system.md").replace("{bu_name}", bu.name)
    user = bu.prompt("advice_user.md").replace(
        "{payload}", json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_advice(text: str) -> list[dict]:
    """解析模型返回的建议数组。

    大模型(Qwen 等)经常不吐纯 JSON:带前言后语、未转义引号、中文逗号、尾逗号,
    都会让整段 json.loads 直接炸。这里不假设模型语法完美,三层兜底:
      1. 剥围栏 + 截取首个 [ 到末个 ] 之间的数组体,扔掉解释文字;
      2. 整体解析一次(绝大多数走这条);
      3. 整体失败,再括号配平逐个救 {...},坏的跳过,保住其余建议——
         避免"一条坏全降级到规则"。
    """
    if not text:
        return []
    fence = chr(96) * 3
    t = text.strip().replace(fence + "json", "").replace(fence, "").strip()

    # 截取数组边界,丢掉模型可能掺的前后解释文字
    start, end = t.find("["), t.rfind("]")
    body = t[start : end + 1] if 0 <= start < end else t

    try:
        data = json.loads(body)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass

    return _salvage_objects(body)


def _salvage_objects(body: str) -> list[dict]:
    """括号配平扫描,把数组里每个 {...} 单独解析,坏的跳过。

    忽略字符串内的花括号(含转义),避免把 suggestion 文本里的 { 当成对象边界。
    """
    items: list[dict] = []
    depth = 0
    in_str = False
    escape = False
    obj_start = -1
    for i, ch in enumerate(body):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start >= 0:
                try:
                    obj = json.loads(body[obj_start : i + 1])
                    if isinstance(obj, dict):
                        items.append(obj)
                except json.JSONDecodeError:
                    pass  # 单条坏掉跳过,保住其余
                obj_start = -1
    return items


def rule_based_advice(insights: dict, bu_dispatch: dict | None = None) -> list[dict]:
    """规则版兜底建议:无模型时基于阈值生成,保证总有可用输出。

    bu_dispatch:BU 分发漏斗统计(两类错误),用于给"如何提升 BU 分发准确率"建议。
    """
    advice: list[dict] = []

    # —— BU 分发层建议(全局,基于两类错误)——
    if bu_dispatch and bu_dispatch.get("scored"):
        acc = bu_dispatch["accuracy"]
        miss = bu_dispatch.get("miss_should_accept_but_rejected", 0)
        over = bu_dispatch.get("over_should_reject_but_accepted", 0)
        if acc < _LOW_DISPATCH:
            cause = "误收(他业务问题被本BU收下)" if over >= miss else "漏收(本应承接却被拒识)"
            fix = ("补拒识规则,把无关问题挡在外面" if over >= miss
                   else "放宽分发/补本BU意图覆盖,别把该接的拒了")
            advice.append({
                "scope": "BU 分发(全局)",
                "severity": "high",
                "problem": f"BU 分发准确率仅 {acc:.0%},主要错误是{cause}",
                "root_cause": "分发问题",
                "suggestion": fix,
                "evidence": f"漏收 {miss} 条 / 误收 {over} 条",
            })

    # —— 解决度层建议(按业务类型切片)——
    for s in insights["by_intent"]:
        if s.get("in_bu_count", 0) < _MIN_SAMPLES or s["name"] == "(未分类)":
            continue
        if s["resolved_rate"] < _LOW_RESOLVED:
            advice.append({
                "scope": s["name"],
                "severity": "medium",
                "problem": f"『{s['name']}』问题解决率仅 {s['resolved_rate']:.0%}",
                "root_cause": "答案问题",
                "suggestion": "分发到本BU但没解决,排查答案质量:补该业务类型的知识库/标问答案,"
                              "或检查答案卡渲染是否完整。",
                "evidence": f"漏斗内 {s['in_bu_count']} 条,解决率 {s['resolved_rate']:.0%},"
                            f"典型未解决:{'、'.join(s['unresolved_examples'][:2]) or '—'}",
            })
        if s["needs_review_rate"] >= _HIGH_REVIEW:
            advice.append({
                "scope": s["name"],
                "severity": "low",
                "problem": f"『{s['name']}』需人工复核率高达 {s['needs_review_rate']:.0%}",
                "root_cause": "需人工",
                "suggestion": "该意图 Judge 置信普遍偏低,建议补充意图定义/示例,或纳入人工复核队列。",
                "evidence": f"需复核率 {s['needs_review_rate']:.0%}",
            })
    # 按严重度排序
    order = {"high": 0, "medium": 1, "low": 2}
    advice.sort(key=lambda a: order.get(a["severity"], 9))
    return advice[:6]
