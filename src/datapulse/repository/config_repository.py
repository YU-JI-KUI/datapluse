"""Config repository - CRUD operations on system_config table."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from datapulse.model.entities import SystemConfig
from datapulse.repository.base import DEFAULT_DATASET_CONFIG

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _deep_merge(base: dict, override: dict) -> None:
    """递归将 override 合并到 base（原地修改，base 为默认值，override 优先）"""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


class ConfigRepository:
    """Repository for SystemConfig entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_dataset_config(self, dataset_id: int) -> dict[str, Any]:
        """读取 dataset 配置并与默认值深度合并（每次直接查 DB，天然热更新）"""
        row = self.session.get(SystemConfig, dataset_id)
        if row is None:
            return copy.deepcopy(DEFAULT_DATASET_CONFIG)
        merged = copy.deepcopy(DEFAULT_DATASET_CONFIG)
        _deep_merge(merged, row.config_data or {})
        return merged

    def set_dataset_config(
        self, dataset_id: int, config_data: dict[str, Any], updated_by: str = "system"
    ) -> dict[str, Any]:
        row = self.session.get(SystemConfig, dataset_id)
        if row is None:
            row = SystemConfig(dataset_id=dataset_id)
            self.session.add(row)
        row.config_data = config_data
        row.updated_at = _now()
        row.updated_by = updated_by
        return config_data
