"""
配置读取模块

启动引导参数通过环境变量注入，本地开发在项目根目录放 .env 文件。
不再依赖 config.yaml，天然适配 Docker / K8s 部署。

必填环境变量：
  DB_HOST   — 主库地址，支持多主机自动故障切换（见下方说明）
  DB_NAME   — 数据库名
  DB_USER   — 数据库用户名
  DB_PASSWORD 或 CyberArk 配置（二选一）

DB_HOST 多主机格式（PostgreSQL libpq 原生支持，psycopg2 2.8+）：
  单主机（含端口）：192.168.1.10:5432
  单主机（用 DB_PORT）：192.168.1.10
  主库 + 灾备（自动故障切换）：192.168.1.10:5432,192.168.1.11:5432
  混合格式：192.168.1.10,192.168.1.11（端口统一使用 DB_PORT）

  多主机模式下，驱动层会按顺序尝试每个节点，跳过不可读写节点（target_session_attrs=read-write）。
  应用无感知，无需手动重启，真正实现主备自动切换。

可选环境变量（有默认值）：
  DB_PORT            默认 5432，多主机未单独指定端口时使用
  STORAGE_BASE_PATH  NAS 基础路径，默认 ./nas
  SECRET_KEY         JWT 签名密钥，生产环境务必替换
  LOG_DIR            日志目录，留空则自动使用 {STORAGE_BASE_PATH}/logs
  APP_ENV            dev / stg / prod，默认 dev

PROD / CyberArk 密码获取：
  DB_PASSWORD 已配置（非空）→ 直接使用
  DB_PASSWORD 未配置且 CYBERARK_APPID 已配置 → 从 CyberArk 动态获取
  两者均未配置 → 启动报错

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
    # DB_HOST 支持多主机格式：host1:port1,host2:port2
    # 未含端口的主机使用 DB_PORT 作为默认端口
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

    # ── CyberArk 配置（DB_PASSWORD 未配置时使用，任意环境均支持）──────────────────
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
        SQLAlchemy 连接 URL。
        - 单主机：postgresql+psycopg2://user:pass@host:port/dbname
        - 多主机：postgresql+psycopg2://user:pass@/dbname
          （host/port 通过 db_connect_args 传入 psycopg2，驱动层自动故障切换）
        """
        password   = self._effective_db_password()
        encoded_pw = _url_quote(password, safe="")
        if self._is_multi_host():
            # 多主机时 URL 中不含 host，由 connect_args 接管
            return f"postgresql+psycopg2://{self.db_user}:{encoded_pw}@/{self.db_name}"
        host, port = self._parse_single_host()
        return f"postgresql+psycopg2://{self.db_user}:{encoded_pw}@{host}:{port}/{self.db_name}"

    @property
    def db_url_safe(self) -> str:
        """脱敏连接信息，用于日志（密码替换为 ***）。"""
        if self._is_multi_host():
            hosts, ports = self._split_hosts()
            pairs = ",".join(f"{h}:{p}" for h, p in zip(hosts, ports))
            return f"postgresql://{self.db_user}:***@{pairs}/{self.db_name}"
        host, port = self._parse_single_host()
        return f"postgresql://{self.db_user}:***@{host}:{port}/{self.db_name}"

    @property
    def db_connect_args(self) -> dict:
        """
        多主机模式下传递给 psycopg2 的 libpq 连接参数。
        单主机返回空字典（host/port 已含在 db_url 中）。

        target_session_attrs=read-write：libpq 只连可读写节点（主库），
        灾备库在主库恢复前保持只读，故障时自动切换到可写节点。
        """
        if not self._is_multi_host():
            return {}
        hosts, ports = self._split_hosts()
        return {
            "host":                 ",".join(hosts),
            "port":                 ",".join(ports),
            "target_session_attrs": "read-write",
        }

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_log_dir(self) -> str:
        """日志目录：LOG_DIR 显式设置时优先，否则自动落到 {storage_base_path}/logs。"""
        return self.log_dir.strip() or f"{self.storage_base_path}/logs"

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() == "prod"

    # ── 内部方法 ──────────────────────────────────────────────────────────────────

    def _is_multi_host(self) -> bool:
        """DB_HOST 含逗号时视为多主机模式。"""
        return "," in self.db_host

    def _split_hosts(self) -> tuple[list[str], list[str]]:
        """将 DB_HOST 解析为 (hosts, ports) 两个列表，未含端口的条目使用 DB_PORT。"""
        hosts, ports = [], []
        for entry in self.db_host.split(","):
            entry = entry.strip()
            if ":" in entry:
                h, p = entry.rsplit(":", 1)
                hosts.append(h.strip())
                ports.append(p.strip())
            else:
                hosts.append(entry)
                ports.append(str(self.db_port))
        return hosts, ports

    def _parse_single_host(self) -> tuple[str, int]:
        """单主机模式：解析 host 与 port（host:port 或仅 host）。"""
        entry = self.db_host.strip()
        if ":" in entry:
            h, p = entry.rsplit(":", 1)
            return h.strip(), int(p)
        return entry, self.db_port

    def _effective_db_password(self) -> str:
        """
        解析实际生效的数据库密码（优先级：DB_PASSWORD > CyberArk）：
          - DB_PASSWORD 已配置（非空）→ 直接使用，不走 CyberArk
          - DB_PASSWORD 未配置且 CYBERARK_APPID 已配置 → 从 CyberArk 获取（进程内缓存）
          - 两者均未配置 → 启动报错，给出明确提示
        """
        if self.db_password:
            return self.db_password

        if self.cyberark_appid:
            from datapulse.config.cyberark import fetch_db_password_from_cyberark
            return fetch_db_password_from_cyberark()

        raise ValueError(
            "数据库密码未配置：请在 .env 中设置 DB_PASSWORD，"
            "或配置 CYBERARK_APPID / CYBERARK_URL 等变量通过 CyberArk 获取密码。"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
