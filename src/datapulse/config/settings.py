"""
配置读取模块

启动引导参数通过环境变量注入，本地开发可在项目根目录放 .env 文件。
不再依赖 config.yaml，彻底消除文件路径问题，天然适配 Docker / K8s 部署。

必填环境变量：
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

可选环境变量（有默认值）：
  STORAGE_BASE_PATH  NAS 基础路径（向量文件、FAISS 索引、日志均存于此），默认 /ark-nav/datapulse
  SECRET_KEY         JWT 签名密钥，生产环境务必替换
  LOG_DIR            日志目录，留空则自动使用 {STORAGE_BASE_PATH}/logs

业务配置（LLM / Embedding / 标签等）存储在 PostgreSQL system_config 表，
通过配置中心 UI 按 dataset 独立管理，支持热更新，与启动配置无关。
"""

from __future__ import annotations

from functools import lru_cache

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
    # JWT 签名密钥，必须通过环境变量注入，禁止 hardcode。
    # 生成：python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str

    # ── NAS 存储 ──────────────────────────────────────────────────────────────
    # 所有 dataset 共用同一 NAS 根目录，向量文件、FAISS 索引均存于此。
    # 子目录结构由各模块自行约定，无需额外配置。
    storage_base_path: str = "./nas"

    # ── Embedding 模型 ────────────────────────────────────────────────────────
    # 所有 dataset 共用同一本地 embedding 模型路径，通过环境变量统一配置。
    # 示例（.env）：EMBEDDING_MODEL_PATH=/ark-nav/models/xiaobu-embedding-v2
    embedding_model_path: str = "/ark-nav/models/xiaobu-embedding-v2"

    # ── 日志配置 ──────────────────────────────────────────────────────────────
    # 运行环境：dev（彩色 console）/ test / prod（JSON console）
    app_env:          str = "dev"
    # 日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL
    log_level:        str = "INFO"
    # 日志文件目录；留空时自动使用 {storage_base_path}/logs
    log_dir:          str = ""
    # 日志轮转策略：time（按天，默认）| size（按文件大小）
    log_rotation:     str = "time"
    # size 轮转时单个文件上限（字节），默认 100 MB
    log_max_bytes:    int = 100 * 1024 * 1024
    # 保留的日志文件/天数（time 轮转保留 N 天，size 轮转保留 N 份）
    log_backup_count: int = 30
    # 服务名称，写入每条日志的 service 字段
    service_name:     str = "datapulse"
    # 实例 ID，多实例部署时区分节点（为空时自动取 hostname）
    instance_id:      str = ""

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
    def effective_log_dir(self) -> str:
        """日志目录：LOG_DIR 显式设置时优先使用，否则自动落到 {storage_base_path}/logs。"""
        return self.log_dir.strip() or f"{self.storage_base_path}/logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
