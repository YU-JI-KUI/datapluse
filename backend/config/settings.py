"""
配置读取模块

config.yaml 仅存放三类启动引导参数：
  - database  ：PostgreSQL 连接信息（必填）
  - storage   ：本地向量文件路径（FAISS 使用）
  - auth      ：JWT 签名密钥

业务配置（LLM / Embedding / 标签等）存储在 PostgreSQL system_config 表，
通过 db.get_dataset_config() 读取，支持每个 dataset 独立配置，支持热更新。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).parent.parent.parent


def _load_yaml() -> dict[str, Any]:
    config_path = _ROOT / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Settings:
    """启动引导配置（单例），只读 config.yaml"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = _load_yaml()

    @property
    def db_url(self) -> str:
        db = self._data["database"]
        return (
            f"postgresql://{db['user']}:{db['password']}"
            f"@{db['host']}:{db['port']}/{db['name']}"
        )

    @property
    def storage_base_path(self) -> Path:
        raw = self._data["storage"]["base_path"]
        p = Path(raw)
        return p if p.is_absolute() else _ROOT / p

    @property
    def secret_key(self) -> str:
        return self._data.get("auth", {}).get("secret_key", "changeme")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
