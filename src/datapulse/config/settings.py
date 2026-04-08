"""
配置读取模块

启动引导参数通过环境变量注入，本地开发可在项目根目录放 .env 文件。
不再依赖 config.yaml，彻底消除文件路径问题，天然适配 Docker / K8s 部署。

必填环境变量：
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

可选环境变量（有默认值）：
  SECRET_KEY        JWT 签名密钥，生产环境务必替换
  STORAGE_BASE_PATH 本地向量文件根目录，默认 ./nas

业务配置（LLM / Embedding / 标签等）存储在 PostgreSQL system_config 表，
通过配置中心 UI 按 dataset 独立管理，支持热更新，与启动配置无关。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 按优先级依次查找 .env 文件：运行目录 → 项目根（向上最多 3 层）
        env_file=(
            ".env",
            "../.env",
            "../../.env",
            "../../../.env",
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── 数据库（必填） ───────────────────────────────────────────────────────────
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str

    # ── 认证 ────────────────────────────────────────────────────────────────────
    secret_key: str = "changeme-replace-in-production"

    # ── 本地存储（向量文件） ──────────────────────────────────────────────────────
    storage_base_path: str = "./nas"

    # ── 计算属性 ─────────────────────────────────────────────────────────────────
    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_base_path)
        return p if p.is_absolute() else Path.cwd() / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
