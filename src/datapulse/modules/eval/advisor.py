"""优化建议生成器（多专项卡片）。

一个维度一张卡：固定 3（分发/解决率/新分类，全局）+ 动态 2N（每分类·分发/解决率）。
每张卡各调一次 LLM、各出一段纯文本 markdown。料由 advice_facts.build_facts 预聚合，
本模块按 token 预算填模板组 prompt（build_card_prompts），无模型时用规则版兜底
（rule_based_cards）。
"""
from __future__ import annotations

from datapulse.modules.eval._settings import settings
from datapulse.modules.eval.bu.base import BUConfig

# ══════════════════════════════════════════════════════════════════════════════
# 多专项建议（新体系）：一个维度一张卡、各调一次 LLM、各出一段纯文本 markdown。
# 卡片体系：固定 3（分发/解决率/新分类，全局）+ 动态 2N（每分类·分发/解决率）。
# 料由 advice_facts.build_facts 预聚合，这里负责按 token 预算填模板、组 prompt。
# ══════════════════════════════════════════════════════════════════════════════

# 中文粗略 token 估算：Qwen 约 1.5~1.7 字/token，取保守 1.7（宁少喂不超窗）。
_CHARS_PER_TOKEN = 1.7


def _est_tokens(text: str) -> int:
    return int(len(text) / _CHARS_PER_TOKEN) + 1


def _sample_budget(system: str, user_skeleton: str) -> int:
    """一张卡可用来塞样例的字符预算（换算回字符，填料时按字符累加更直观）。

    = 上下文窗口 − 骨架(system+user已填统计) − 输出留白，再换算成字符。
    """
    budget_tokens = (settings.advice_ctx_budget
                     - _est_tokens(system) - _est_tokens(user_skeleton)
                     - settings.advice_max_tokens
                     - 512)  # 额外安全余量
    return max(0, int(budget_tokens * _CHARS_PER_TOKEN))


def _fill_examples(examples: list[dict], render, char_budget: int) -> tuple[str, int]:
    """按序把样例渲染进预算，返回 (拼好的文本, 未展示条数)。宁可多喂，逼近上限即止。"""
    parts: list[str] = []
    used = 0
    shown = 0
    for ex in examples:
        block = render(ex)
        if used + len(block) > char_budget and shown > 0:
            break
        parts.append(block)
        used += len(block)
        shown += 1
    remaining = len(examples) - shown
    return "\n".join(parts), remaining


def _more_note(remaining: int) -> str:
    return f"\n\n> 另有 {remaining} 条同类样例未展示（受长度限制），实际规模更大。" if remaining > 0 else ""


def _render_dispatch_ex(ex: dict) -> str:
    return (f"- 问题：{ex['question']}\n"
            f"  判断依据：{ex.get('dispatch_reason', '') or '—'}")


def _render_resolved_ex(ex: dict) -> str:
    tag = ex.get("unresolved_cause") or "未归类"
    intent = f"（{ex['intent']}）" if ex.get("intent") else ""
    return (f"- 问题{intent}：{ex['question']}\n"
            f"  AI 答案：{ex.get('answer_text', '') or '—'}\n"
            f"  未解决原因：{tag}")


def _card_messages(bu: BUConfig, user_tpl_name: str, payload_text: str,
                   intent_name: str | None = None) -> list[dict]:
    """组一张卡的 system+user 消息（system 共用 advice_card_system.md）。"""
    system = bu.prompt("advice_card_system.md").replace("{bu_name}", bu.name)
    user = bu.prompt(user_tpl_name).replace("{payload}", payload_text)
    if intent_name is not None:
        user = user.replace("{intent_name}", intent_name)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_card_prompts(facts: dict, insights: dict, bu: BUConfig,
                       bu_dispatch: dict | None = None) -> list[dict]:
    """产出全部卡片的 prompt 规格：[{id, title, dimension, category, messages}]。

    facts 由 build_facts 预聚合；样例按每卡 token 预算裁，尽量喂满上下文窗口。
    facts 为空（未落盘 / 测试路径）→ 返回空列表，编排层走 rule 兜底。
    """
    if not facts or not facts.get("dispatch_global"):
        return []
    system = bu.prompt("advice_card_system.md").replace("{bu_name}", bu.name)
    cards: list[dict] = []

    # ① 全局分发诊断
    dg = facts["dispatch_global"]
    skel = bu.prompt("advice_dispatch_global.md")
    budget = _sample_budget(system, skel)
    miss_txt, miss_rest = _fill_examples(dg["miss_examples"], _render_dispatch_ex, budget // 2)
    over_txt, over_rest = _fill_examples(dg["over_examples"], _render_dispatch_ex, budget // 2)
    payload = (
        f"分发准确率：{_pct(dg.get('accuracy'))}\n"
        f"漏收（该分未分）总数：{dg.get('miss_count')}；误收（该拒未拒）总数：{dg.get('over_count')}\n\n"
        f"## 高频被漏收问题（问题, 次数）\n{_fmt_top(dg['top_missed'])}\n\n"
        f"## 高频被误收问题（问题, 次数）\n{_fmt_top(dg['top_over'])}\n\n"
        f"## 漏收样例\n{miss_txt or '—'}{_more_note(miss_rest)}\n\n"
        f"## 误收样例\n{over_txt or '—'}{_more_note(over_rest)}"
    )
    cards.append({
        "id": "dispatch::global", "title": "分发问题诊断", "dimension": "分发",
        "category": "全局",
        "messages": _card_messages(bu, "advice_dispatch_global.md", payload),
    })

    # ② 全局解决率诊断
    rg = facts["resolved_global"]
    skel = bu.prompt("advice_resolved_global.md")
    budget = _sample_budget(system, skel)
    ex_txt, ex_rest = _fill_examples(rg["examples"], _render_resolved_ex, budget)
    payload = (
        f"整体问题解决率：{_pct(insights.get('overall', {}).get('resolved_rate'))}\n\n"
        f"## 未解决四归因全局分布\n{_fmt_dist(rg['unresolved_dist'])}\n\n"
        f"## 未解决样例（跨分类）\n{ex_txt or '—'}{_more_note(ex_rest)}"
    )
    cards.append({
        "id": "resolved::global", "title": "全局解决率诊断", "dimension": "解决率",
        "category": "全局",
        "messages": _card_messages(bu, "advice_resolved_global.md", payload),
    })

    # ③ 新业务分类发现
    nb = facts["new_business"]
    skel = bu.prompt("advice_new_business.md")
    budget = _sample_budget(system, skel)
    q_txt, q_rest = _fill_examples(
        [{"q": q, "n": n} for q, n in nb["questions"]],
        lambda e: f"- {e['q']}（{e['n']} 次）", budget)
    payload = (
        f"被判「非本BU」的问题：共 {nb['count']} 条、去重 {nb['distinct']} 个\n\n"
        f"## 问题清单（问题, 出现次数）\n{q_txt or '—'}{_more_note(q_rest)}"
    )
    cards.append({
        "id": "new_business::global", "title": "新业务分类发现", "dimension": "新分类",
        "category": "全局",
        "messages": _card_messages(bu, "advice_new_business.md", payload),
    })

    # ④⑤ 逐分类·分发提升 / 解决率提升
    for name, f in facts["by_intent"].items():
        # ④ 分发
        skel = bu.prompt("advice_intent_dispatch.md")
        budget = _sample_budget(system, skel)
        d_txt, d_rest = _fill_examples(f["dispatch_examples"], _render_dispatch_ex, budget)
        payload = f"分类：{name}\n\n## 分发失败样例\n{d_txt or '—'}{_more_note(d_rest)}"
        cards.append({
            "id": f"intent::{name}::dispatch", "title": f"{name}·分发提升",
            "dimension": "分发", "category": name,
            "messages": _card_messages(bu, "advice_intent_dispatch.md", payload, intent_name=name),
        })
        # ⑤ 解决率
        skel = bu.prompt("advice_intent_resolved.md")
        budget = _sample_budget(system, skel)
        u_txt, u_rest = _fill_examples(f["unresolved_examples"], _render_resolved_ex, budget)
        payload = (
            f"分类：{name}\n"
            f"进漏斗 {f['in_bu']} 条，解决率 {_pct(f['resolved_rate'])}\n\n"
            f"## 未解决四归因分布\n{_fmt_dist(f['unresolved_dist'])}\n\n"
            f"## 未解决样例\n{u_txt or '—'}{_more_note(u_rest)}"
        )
        cards.append({
            "id": f"intent::{name}::resolved", "title": f"{name}·解决率提升",
            "dimension": "解决率", "category": name,
            "messages": _card_messages(bu, "advice_intent_resolved.md", payload, intent_name=name),
        })

    return cards


def _pct(v) -> str:
    return "—" if v is None else f"{v:.0%}"


def _fmt_top(pairs: list) -> str:
    return "\n".join(f"- {q}（{n} 次）" for q, n in pairs) or "—"


def _fmt_dist(dist: dict) -> str:
    if not dist:
        return "—"
    return "\n".join(f"- {k}：{v} 条" for k, v in sorted(dist.items(), key=lambda x: -x[1]))


def rule_based_cards(facts: dict, insights: dict, bu: BUConfig,
                     bu_dispatch: dict | None = None) -> list[dict]:
    """规则版卡片：无模型 / 全败时兜底，用 build_facts 的料渲染成同构 markdown 文本卡。

    mock 后端也走这里，保证离线也能端到端验证卡片结构与前端渲染。
    """
    cards: list[dict] = []
    fd = facts.get("dispatch_global") if facts else None

    # ① 分发
    if fd:
        lines = [f"**分发准确率**：{_pct(fd.get('accuracy'))}",
                 f"漏收 {fd.get('miss_count')} 条 / 误收 {fd.get('over_count')} 条。", ""]
        if fd["top_missed"]:
            lines.append("**高频被漏收问题**：")
            lines += [f"- {q}（{n} 次）" for q, n in fd["top_missed"][:10]]
        if fd["top_over"]:
            lines.append("\n**高频被误收问题**：")
            lines += [f"- {q}（{n} 次）" for q, n in fd["top_over"][:10]]
        lines.append("\n> 规则生成：漏收多→补意图覆盖/放宽分发；误收多→补拒识规则。")
        cards.append({"id": "dispatch::global", "title": "分发问题诊断",
                      "dimension": "分发", "category": "全局", "text": "\n".join(lines)})

    # ② 全局解决率
    rg = facts.get("resolved_global") if facts else None
    if rg:
        lines = [f"**整体解决率**：{_pct(insights.get('overall', {}).get('resolved_rate'))}", "",
                 "**未解决四归因分布**：", _fmt_dist(rg["unresolved_dist"]),
                 "\n> 规则生成：占比最高的一类即当前最该攻克的方向。"]
        cards.append({"id": "resolved::global", "title": "全局解决率诊断",
                      "dimension": "解决率", "category": "全局", "text": "\n".join(lines)})

    # ③ 新业务分类
    nb = facts.get("new_business") if facts else None
    if nb and nb["count"]:
        lines = [f"被判「非本BU」共 {nb['count']} 条、去重 {nb['distinct']} 个。", "",
                 "**高频非本BU问题**："]
        lines += [f"- {q}（{n} 次）" for q, n in nb["questions"][:15]]
        lines.append("\n> 规则生成：反复出现的问题簇可考虑提炼为新业务分类。")
        cards.append({"id": "new_business::global", "title": "新业务分类发现",
                      "dimension": "新分类", "category": "全局", "text": "\n".join(lines)})

    # ④⑤ 逐分类
    for name, f in (facts.get("by_intent") if facts else {}).items():
        if f["dispatch_examples"]:
            lines = [f"分类 **{name}** 分发失败样例（漏收/误收）："]
            lines += [f"- {ex['question']}（{ex.get('scene', '')}）" for ex in f["dispatch_examples"][:10]]
            cards.append({"id": f"intent::{name}::dispatch", "title": f"{name}·分发提升",
                          "dimension": "分发", "category": name, "text": "\n".join(lines)})
        if f["in_bu"]:
            lines = [f"分类 **{name}**：进漏斗 {f['in_bu']} 条，解决率 {_pct(f['resolved_rate'])}", "",
                     "**未解决四归因**：", _fmt_dist(f["unresolved_dist"])]
            cards.append({"id": f"intent::{name}::resolved", "title": f"{name}·解决率提升",
                          "dimension": "解决率", "category": name, "text": "\n".join(lines)})

    return cards
