"""BU 注册表:按 code 取 BUConfig。

BU 本体（code/name/描述/mock 规则/样例）仍是代码常量；业务分类（intents）改为
按当前库/文件动态注入——get_bu 每次用 load_categories 取最新分类，replace 进
BUConfig，故页面增删改分类后不重启即生效。
"""
from __future__ import annotations

from dataclasses import replace

from datapulse.modules.eval.bu.base import BUConfig, load_activity_questions, load_categories
from datapulse.modules.eval.bu.life_insurance import LIFE
from datapulse.modules.eval.bu.securities import SECURITIES

# 模板（不含 intents，intents 在 get_bu 动态注入）
_TEMPLATES: dict[str, BUConfig] = {
    SECURITIES.code: SECURITIES,
    LIFE.code: LIFE,
}

DEFAULT_BU = SECURITIES.code


def bu_codes() -> list[str]:
    return list(_TEMPLATES.keys())


def get_bu(code: str | None) -> BUConfig:
    """按 code 取 BU 配置;未知或空回默认。

    intents（业务分类）与 activity_questions（活动标问）均注入当前库中的值,作为
    快照固化进 frozen BUConfig,故页面改了不重启即生效、且任务中途不变。
    """
    tpl = _TEMPLATES.get(code or DEFAULT_BU, _TEMPLATES[DEFAULT_BU])
    return replace(
        tpl,
        intents=load_categories(tpl.code),
        activity_questions=load_activity_questions(tpl.code),
    )


def list_bus() -> list[dict]:
    """列出所有可选 BU,供前端选择器（intent_count 按当前分类数）。"""
    out = []
    for tpl in _TEMPLATES.values():
        out.append({
            "code": tpl.code, "name": tpl.name,
            "description": tpl.description, "intent_count": len(load_categories(tpl.code)),
        })
    return out
