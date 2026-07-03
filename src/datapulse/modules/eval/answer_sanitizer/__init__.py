"""答案净化：把 Excel 原始答案（常是整坨 JSON 渲染卡）提取成人类/模型可读正文。

对外只暴露 sanitize_answer(raw, bu_code)，签名与旧版一致。内部用「一种答案结构 =
一个 AnswerParser 子类」的插件式框架：

  base.py         抽象基类 AnswerParser + 注册机制 + 公用工具（dig/strip_html…）
  generic.py      通用解析器（所有 BU）：content_data / LLM API 响应
  securities.py   证券专属：小安渲染卡（含同花顺、列表卡片）
  life.py …       寿险等 BU 的专属解析器（内网新增：新写一个文件即可）

新增一种答案类型：写一个子类（match 判结构、parse 提正文）+ @register，声明 bu_codes；
不改入口、不改主流程。匹配顺序：当前 BU 专属优先 → 回退通用 → 都不命中保留原文截断。
"""
from __future__ import annotations

from datapulse.modules.eval.answer_sanitizer.base import parse_json, parsers_for, truncate

# 导入子模块以触发 @register 注册（顺序不影响，入口按 bu_codes/priority 排序）。
# 新增 BU 专属解析器文件后，加到这里一并导入即可（如 life_insurance）。
from datapulse.modules.eval.answer_sanitizer import (  # noqa: E402,F401
    generic,
    life_insurance,
    securities,
)

__all__ = ["sanitize_answer", "diagnose"]


def _bu_code(bu) -> str:
    """兼容调用方传 bu_code 字符串或 BUConfig 对象。"""
    return getattr(bu, "code", bu) or ""


def sanitize_answer(raw: str, bu=None) -> str:
    """把原始答案净化成人类/模型可读的正文。空/非字符串原样返回；任何异常保留原文。

    bu：BU code 字符串，或 BUConfig 对象（取其 .code）。据此挑选适用的解析器：
    专属优先、未命中回退通用、都不命中保留原文（超长截断防爆）。
    """
    if not raw or not isinstance(raw, str):
        return raw
    try:
        code = _bu_code(bu)
        parsed = parse_json(raw)
        for p in parsers_for(code):
            try:
                if p.match(raw, parsed):
                    got = p.parse(raw, parsed)
                    if got:
                        return got
            except Exception:
                continue   # 单个解析器出错不影响其它，继续下一个
        return truncate(raw)   # 都不命中：保留原文但截断（不丢关键信息，又防爆）
    except Exception:
        return raw   # 净化绝不丢数据


def diagnose(raw: str, bu=None) -> dict:
    """诊断某条答案：命中了哪个解析器 / 是不是 JSON / 提取是否成功。供覆盖率排查脚本用。

    返回 {"parser": 命中的解析器名 或 None, "is_json": bool, "matched": bool}。
    matched=False 即「漏网之鱼」——没有任何解析器认领，当前只能原文兜底。
    """
    if not raw or not isinstance(raw, str):
        return {"parser": None, "is_json": False, "matched": False}
    code = _bu_code(bu)
    parsed = parse_json(raw)
    for p in parsers_for(code):
        try:
            if p.match(raw, parsed) and p.parse(raw, parsed):
                return {"parser": p.name, "is_json": parsed is not None, "matched": True}
        except Exception:
            continue
    return {"parser": None, "is_json": parsed is not None, "matched": False}
