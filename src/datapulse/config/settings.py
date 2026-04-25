"""
配置读取模块

启动引导参数通过环境变量注入，本地开发在项目根目录放 .env 文件。
不再依赖 config.yaml，天然适配 Docker / K8s 部署。

环境区分（APP_ENV）：
  dev  — 本地开发，DB 密码来自 .env 的 DB_PASSWORD
  stg  — 测试环境，DB 密码来自 .env 的 DB_PASSWORD
  prod — 生产环境，DB 密码由 CyberArk 动态获取，.env 中 DB_PASSWORD 可留空

必填环境变量：
  DB_HOST, DB_PORT, DB_NAME, DB_USER
  非 PROD：DB_PASSWORD
  PROD：CYBERARK_URL, CYBERARK_APPID, CYBERARK_KEY, CYBERARK_SAFE, CYBERARK_OBJECT

可选环境变量（有默认值）：
  STORAGE_BASE_PATH  NAS 基础路径，默认 ./nas
  SECRET_KEY         JWT 签名密钥，生产环境务必替换
  LOG_DIR            日志目录，留空则自动使用 {STORAGE_BASE_PATH}/logs

业务配置（LLM / Embedding / 标签等）存储在 PostgreSQL t_system_config 表，
通过配置中心 UI 按 dataset 独立管理，支持热更新，与启动配置无关。
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote as _url_quote

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

    # ── 数据库连接 ────────────────────────────────────────────────────────────────
    # 非 PROD 环境：DB_PASSWORD 必填
    # PROD 环境：DB_PASSWORD 可留空，密码由 CyberArk 动态获取
    db_host:     str
    db_port:     int = 5432
    db_name:     str
    db_user:     str
    db_password: str = ""

    # ── 认证 ─────────────────────────────────────────────────────────────────────
    # JWT 签名密钥，生产环境必须通过环境变量注入，禁止 hardcode
    # 生成：python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str

    # ── NAS 存储 ──────────────────────────────────────────────────────────────────
    storage_base_path: str = "./nas"

    # ── Embedding 模型 ────────────────────────────────────────────────────────────
    # 所有 dataset 共用同一本地 embedding 模型，路径通过 env 统一配置
    embedding_model_path: str = "/ark-nav/models/xiaobu-embedding-v2"

    # ── 运行环境 & 日志 ───────────────────────────────────────────────────────────
    # app_env: dev（彩色 console）/ stg / prod（JSON console，触发 CyberArk）
    app_env:          str = "dev"
    log_level:        str = "INFO"
    log_dir:          str = ""
    log_rotation:     str = "time"
    log_max_bytes:    int = 100 * 1024 * 1024
    log_backup_count: int = 30
    instance_id:      str = ""

    # ── CyberArk 配置（仅 PROD 环境需要，其他环境留默认空值即可）─────────────────
    cyberark_url:     str = ""
    cyberark_appid:   str = ""
    cyberark_key:     str = ""
    cyberark_safe:    str = ""
    cyberark_folder:  str = "root"
    cyberark_object:  str = ""
    cyberark_version: str = "2.0"

    # ── 计算属性 ──────────────────────────────────────────────────────────────────

    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_url(self) -> str:
        """
        数据库连接 URL。
        PROD 环境密码由 CyberArk 动态获取；其他环境直接使用 DB_PASSWORD。
        """
        password   = self._effective_db_password()
        # URL-encode 密码，兼容含特殊字符（$、@、# 等）的密码
        encoded_pw = _url_quote(password, safe="")
        return (
            f"postgresql://{self.db_user}:{encoded_pw}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_log_dir(self) -> str:
        """日志目录：LOG_DIR 显式设置时优先，否则自动落到 {storage_base_path}/logs。"""
        return self.log_dir.strip() or f"{self.storage_base_path}/logs"

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() == "prod"

    # ── 内部方法 ──────────────────────────────────────────────────────────────────

    def _effective_db_password(self) -> str:
        """
        解析实际生效的数据库密码：
          - APP_ENV=prod 且已配置 CYBERARK_APPID → 从 CyberArk 获取（进程内缓存）
          - 其他环境 → 直接返回 DB_PASSWORD（为空时给出明确错误）
        """
        if self.is_prod and self.cyberark_appid:
            from datapulse.config.cyberark import fetch_db_password_from_cyberark
            return fetch_db_password_from_cyberark()

        if not self.db_password:
            raise ValueError(
                "DB_PASSWORD 未配置。"
                "非 PROD 环境请在 .env 中设置 DB_PASSWORD；"
                "PROD 环境请配置 CYBERARK_* 变量并设置 APP_ENV=prod。"
            )
        return self.db_password


@lru_cache
def get_settings() -> Settings:
    return Settings()
