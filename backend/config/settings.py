"""
配置读取模块

两层配置：
  1. config.yaml  ── 启动引导层（数据库连接 + 向量文件路径），不支持热更新
  2. PostgreSQL    ── 业务配置层（LLM / Embedding / 相似度 / Pipeline / 标签）
                     每个 dataset 独立一行，通过 get_dataset_config() 读取，支持热更新

auth 信息已迁移至数据库用户表，config.yaml 中无需配置。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).parent.parent.parent


def _load_yaml() -> dict[str, Any]:
    config_path = ROOT_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Settings:
    """启动引导配置（单例），只读 config.yaml 中的数据库连接和存储路径"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        self._data = _load_yaml()

    # ── 数据库连接（必须在 YAML 中配置，启动时需要） ─────────────────────────
    @property
    def db_url(self) -> str:
        db = self._data["database"]
        return (
            f"postgresql://{db['user']}:{db['password']}"
            f"@{db['host']}:{db['port']}/{db['name']}"
        )

    # ── 向量文件存储路径（FAISS 需要本地文件） ───────────────────────────────
    @property
    def storage_base_path(self) -> Path:
        raw = self._data["storage"]["base_path"]
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT_DIR / p
        return p

    # ── JWT 密钥（保留在 YAML，重启不失效） ─────────────────────────────────
    @property
    def secret_key(self) -> str:
        return self._data.get("auth", {}).get("secret_key", "changeme-please-set-in-config")

    # ── 首次迁移：如果 YAML 中仍有旧版 auth 配置，返回用于自动创建管理员 ────
    @property
    def legacy_admin_username(self) -> str | None:
        return self._data.get("auth", {}).get("admin_username")

    @property
    def legacy_admin_password(self) -> str | None:
        return self._data.get("auth", {}).get("admin_password")

    # ── 原始 YAML 数据（config API 使用） ────────────────────────────────────
    @property
    def raw(self) -> dict[str, Any]:
        return self._data


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
