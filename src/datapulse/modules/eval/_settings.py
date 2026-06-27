"""评测模块的配置适配层。

ark-dialog-eval 核心代码以模块级 `from ... import settings` 方式使用配置，
datapulse 用 `get_settings()` 单例。此处用同名对象桥接，核心层无需改动。
"""
from __future__ import annotations

from datapulse.config.settings import get_settings

settings = get_settings()
