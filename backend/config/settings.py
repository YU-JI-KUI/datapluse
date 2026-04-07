"""
配置中心 - 从 config.yaml 加载，支持热更新
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.parent


def _load_yaml() -> dict[str, Any]:
    config_path = ROOT_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data: dict[str, Any]) -> None:
    config_path = ROOT_DIR / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


class Settings:
    """运行时配置（单例，支持 reload）"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        self._data = _load_yaml()

    # ── embedding ──────────────────────────────────────────────────────────
    @property
    def embedding_model_path(self) -> str:
        return self._data["embedding"]["model_path"]

    @property
    def embedding_batch_size(self) -> int:
        return self._data["embedding"]["batch_size"]

    @property
    def embedding_use_mock(self) -> bool:
        return self._data["embedding"].get("use_mock", True)

    # ── similarity ─────────────────────────────────────────────────────────
    @property
    def similarity_threshold_high(self) -> float:
        return self._data["similarity"]["threshold_high"]

    @property
    def similarity_threshold_mid(self) -> float:
        return self._data["similarity"]["threshold_mid"]

    @property
    def similarity_topk(self) -> int:
        return self._data["similarity"]["topk"]

    # ── pipeline ───────────────────────────────────────────────────────────
    @property
    def pipeline_batch_size(self) -> int:
        return self._data["pipeline"]["batch_size"]

    # ── storage ────────────────────────────────────────────────────────────
    @property
    def storage_base_path(self) -> Path:
        raw = self._data["storage"]["base_path"]
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT_DIR / p
        return p

    # ── auth ───────────────────────────────────────────────────────────────
    @property
    def admin_username(self) -> str:
        return self._data["auth"]["admin_username"]

    @property
    def admin_password(self) -> str:
        return self._data["auth"]["admin_password"]

    @property
    def secret_key(self) -> str:
        return self._data["auth"].get("secret_key", "changeme")

    # ── llm ────────────────────────────────────────────────────────────────
    @property
    def llm_api_url(self) -> str:
        return self._data["llm"]["api_url"]

    @property
    def llm_model_name(self) -> str:
        return self._data["llm"]["model_name"]

    @property
    def llm_use_mock(self) -> bool:
        return self._data["llm"].get("use_mock", True)

    @property
    def llm_timeout(self) -> int:
        return self._data["llm"].get("timeout", 30)

    # ── labels ─────────────────────────────────────────────────────────────
    @property
    def labels(self) -> list[str]:
        return self._data.get("labels", ["寿险意图", "拒识"])

    # ── raw access ─────────────────────────────────────────────────────────
    @property
    def raw(self) -> dict[str, Any]:
        return self._data

    def update(self, new_data: dict[str, Any]) -> None:
        """覆盖更新并持久化"""
        self._data = new_data
        save_yaml(new_data)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
