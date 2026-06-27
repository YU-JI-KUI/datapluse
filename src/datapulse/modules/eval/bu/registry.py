"""BU 注册表:按 code 取 BUConfig。新增 BU 在这里登记即可。"""
from __future__ import annotations

from datapulse.modules.eval.bu.base import BUConfig
from datapulse.modules.eval.bu.life_insurance import LIFE
from datapulse.modules.eval.bu.securities import SECURITIES

_REGISTRY: dict[str, BUConfig] = {
    SECURITIES.code: SECURITIES,
    LIFE.code: LIFE,
}

DEFAULT_BU = SECURITIES.code


def get_bu(code: str | None) -> BUConfig:
    """按 code 取 BU 配置;未知或空则回默认(证券)。"""
    return _REGISTRY.get(code or DEFAULT_BU, _REGISTRY[DEFAULT_BU])


def list_bus() -> list[dict]:
    """列出所有可选 BU,供前端选择器。"""
    return [
        {"code": c.code, "name": c.name, "description": c.description, "intent_count": len(c.intents)}
        for c in _REGISTRY.values()
    ]
