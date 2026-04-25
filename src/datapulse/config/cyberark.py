"""
CyberArk AIM 密码客户端（平安内部 CCP Central Credential Provider 平台）

Application Identity Manager（应用身份管理器）

功能：
  - 通过 CCP REST API 从 CyberArk 密码保险箱获取密码
  - 支持 AES-ECB（v1.0）和 AES-CBC（v2.0）两种解密协议
  - 内置重试机制（默认 5 次，失败时抛出 CyberArkError）
  - 进程内 lru_cache 缓存：相同参数只调用 CyberArk 一次，避免重复网络请求

用法：
  # 推荐：通过 Settings 自动构建（无需手动传参）
  password = fetch_db_password_from_cyberark()

  # 显式构建
  client = CyberArkClient(url=..., appid=..., key=..., safe=..., folder=..., version="2.0")
  password = client.get_password("PG_ARKPG_ARKPGOPR")

参考内部示例（cybark-formal-version1.py）逐字对齐，保持与平台协议一致。
"""

from __future__ import annotations

import hashlib
import json
from binascii import a2b_hex
from functools import lru_cache

import httpx
import structlog
from Crypto.Cipher import AES  # pycryptodome

_log = structlog.get_logger(__name__)

# CCP 平台 CBC 模式固定 IV，与平台协议绑定，禁止修改
_CBC_IV = "pidms20180327!@#"


# ── 异常 ────────────────────────────────────────────────────────────────────────

class CyberArkError(RuntimeError):
    """CyberArk 调用失败（重试耗尽 / 解密失败 / 配置缺失）时抛出。"""


# ── 客户端 ───────────────────────────────────────────────────────────────────────

class CyberArkClient:
    """
    平安内部 CCP（CyberArk）密码客户端。

    所有参数均来自运维颁发的接入凭证：
      url     — CCP REST 接口地址（dev/test/prod 各不同，必须由运维确认）
      appid   — 应用标识（AppId）
      key     — 签名 & 解密密钥（Key）
      safe    — 密码保险箱名称（Safe）
      folder  — 密码目录（Folder），通常为 "root"
      version — 解密协议版本："1.0" → AES-ECB；"2.0" → AES-CBC（推荐）
      retries — 请求失败后的最大重试次数（默认 5）
      timeout — 单次请求超时秒数（默认 10）
    """

    def __init__(
        self,
        url:     str,
        appid:   str,
        key:     str,
        safe:    str,
        folder:  str = "root",
        version: str = "2.0",
        retries: int = 5,
        timeout: int = 10,
    ) -> None:
        if not all([url, appid, key, safe]):
            raise CyberArkError(
                "CyberArkClient 初始化失败：url / appid / key / safe 均为必填参数"
            )
        self._url     = url
        self._appid   = appid
        self._key     = key
        self._safe    = safe
        self._folder  = folder
        self._version = version
        self._retries = retries
        self._timeout = timeout

    # ── 签名（对齐内部示例 getsign 方法）────────────────────────────────────────

    def _getsign(self, appid: str, keyvalue: str) -> str:
        """签名算法：SHA256(appid + '&' + keyvalue)，十六进制小写。"""
        sha256 = hashlib.sha256()
        sha256.update(f"{appid}&{keyvalue}".encode("utf-8"))
        return sha256.hexdigest()

    # ── 解密（对齐内部示例 decodepassword / decodepassword2）───────────────────

    @staticmethod
    def _unpad(data: bytes) -> bytes:
        """PKCS7 去填充。"""
        return data[: -data[-1]]

    def _decrypt_ecb(self, key: str, psw: str) -> str:
        """AES-ECB 解密（version=1.0）。"""
        cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
        return self._unpad(cipher.decrypt(a2b_hex(psw))).decode("utf-8")

    def _decrypt_cbc(self, key: str, psw: str) -> str:
        """AES-CBC 解密（version=2.0），IV 固定为 CCP 平台约定值。"""
        cipher = AES.new(
            key.encode("utf-8"),
            AES.MODE_CBC,
            _CBC_IV.encode("utf-8"),
        )
        return self._unpad(cipher.decrypt(a2b_hex(psw))).decode("utf-8")

    def _decrypt(self, key: str, psw: str) -> str:
        if self._version == "1.0":
            return self._decrypt_ecb(key, psw)
        return self._decrypt_cbc(key, psw)

    # ── 核心接口 ──────────────────────────────────────────────────────────────────

    def get_password(self, object_name: str) -> str:
        """
        从 CyberArk 获取指定 Object 的明文密码。

        Args:
            object_name: CyberArk 凭证对象名称（如 "PG_ARKPG_ARKPGOPR"）

        Returns:
            解密后的明文密码字符串

        Raises:
            CyberArkError: 重试全部失败 / 平台返回错误码 / 解密失败
        """
        sign    = self._getsign(self._appid, self._key)
        payload = {
            "appId":       self._appid,
            "safe":        self._safe,
            "folder":      self._folder,
            "object":      object_name,
            "sign":        sign,
            "encrypt_ver": self._version,
        }
        headers     = {"Content-Type": "application/json"}
        last_err: Exception | None = None

        for attempt in range(1, self._retries + 1):
            try:
                _log.debug(
                    "cyberark.request",
                    attempt=attempt,
                    object=object_name,
                    safe=self._safe,
                    appid=self._appid,
                )
                with httpx.Client(verify=False, timeout=self._timeout) as client:
                    rsp = client.post(
                        self._url,
                        content=json.dumps(payload),
                        headers=headers,
                    )

                body: dict = rsp.json()

                if rsp.status_code == 200 and int(body.get("code", -1)) == 200:
                    encrypted = body["password"]
                    password  = self._decrypt(self._key, encrypted)
                    _log.info(
                        "cyberark.password_fetched",
                        object=object_name,
                        safe=self._safe,
                        version=self._version,
                    )
                    return password

                _log.warning(
                    "cyberark.bad_response",
                    attempt=attempt,
                    http_status=rsp.status_code,
                    code=body.get("code"),
                    message=body.get("message", ""),
                )
                last_err = CyberArkError(
                    f"CyberArk 返回非 200（HTTP {rsp.status_code}），"
                    f"code={body.get('code')}，msg={body.get('message')}"
                )

            except CyberArkError:
                raise
            except Exception as exc:
                _log.warning(
                    "cyberark.request_failed",
                    attempt=attempt,
                    error=str(exc),
                )
                last_err = exc

        raise CyberArkError(
            f"CyberArk 获取密码失败（已重试 {self._retries} 次），"
            f"object={object_name}，最后错误: {last_err}"
        ) from last_err

    # ── 工厂方法 ──────────────────────────────────────────────────────────────────

    @classmethod
    def from_settings(cls) -> "CyberArkClient":
        """从全局 Settings 自动构建客户端实例（推荐在启动时调用一次）。"""
        from datapulse.config.settings import get_settings
        s = get_settings()
        _validate_cyberark_settings(s)
        return cls(
            url     = s.cyberark_url,
            appid   = s.cyberark_appid,
            key     = s.cyberark_key,
            safe    = s.cyberark_safe,
            folder  = s.cyberark_folder,
            version = s.cyberark_version,
        )


# ── 模块级便捷函数（进程内缓存）────────────────────────────────────────────────


def _validate_cyberark_settings(s: object) -> None:
    """检查 CyberArk 必要配置是否齐全，缺失时给出明确错误。"""
    required = {
        "CYBERARK_URL":    getattr(s, "cyberark_url",    ""),
        "CYBERARK_APPID":  getattr(s, "cyberark_appid",  ""),
        "CYBERARK_KEY":    getattr(s, "cyberark_key",    ""),
        "CYBERARK_SAFE":   getattr(s, "cyberark_safe",   ""),
        "CYBERARK_OBJECT": getattr(s, "cyberark_object", ""),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise CyberArkError(
            f"PROD 环境 CyberArk 配置缺失，请在 .env.prod 中设置: {', '.join(missing)}"
        )


@lru_cache(maxsize=None)
def _cached_fetch(
    url: str,
    appid: str,
    key: str,
    safe: str,
    folder: str,
    version: str,
    object_name: str,
) -> str:
    """
    进程内唯一入口，lru_cache 保证相同参数只调用 CyberArk 一次。
    参数均为字符串（hashable），适合 lru_cache。
    """
    client = CyberArkClient(
        url=url, appid=appid, key=key,
        safe=safe, folder=folder, version=version,
    )
    return client.get_password(object_name)


def fetch_db_password_from_cyberark() -> str:
    """
    从 CyberArk 获取数据库密码（PROD 专用）。

    自动读取 Settings 中的 CYBERARK_* 配置，结果进程内永久缓存，
    不会重复发起网络请求。

    Raises:
        CyberArkError: 配置缺失 / 请求失败 / 解密异常
    """
    from datapulse.config.settings import get_settings
    s = get_settings()
    _validate_cyberark_settings(s)
    return _cached_fetch(
        url         = s.cyberark_url,
        appid       = s.cyberark_appid,
        key         = s.cyberark_key,
        safe        = s.cyberark_safe,
        folder      = s.cyberark_folder,
        version     = s.cyberark_version,
        object_name = s.cyberark_object,
    )
