"""平安网关双签名。

平安大模型调用需要两个签名,逻辑搬自 ark_navigator,不要改动算法:
  - RSA 签名(openApiSignature):RSA 私钥对毫秒时间戳做 SHA256 → 科技网关鉴权
  - HMAC 签名(gpt_signature):app_secret 对参数做 HMAC-SHA1 → 应用层鉴权

注意:不是 OpenAI 的 Authorization: Bearer 模式,所以无法用 openai SDK。
"""
from __future__ import annotations

import base64
import binascii
import hmac
from urllib.parse import urlencode

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5


def get_open_api_sign(rsa_private_key: str, request_time: str) -> str:
    """openApiSignature:RSA 私钥(十六进制 DER)对 requestTime 做 SHA256+PKCS1 签名。

    Args:
        rsa_private_key: 十六进制字符串形式的 RSA 私钥(科技网关下发)
        request_time: 毫秒时间戳字符串,必须与 header 里的 openApiRequestTime 一致
    Returns:
        大写十六进制签名串
    """
    binary_key = binascii.a2b_hex(rsa_private_key)
    pkcs8_private_key = RSA.import_key(binary_key)
    h = SHA256.new(request_time.encode("utf-8"))
    signer = PKCS1_v1_5.new(pkcs8_private_key)
    signature = signer.sign(h).hex().upper()
    return signature


def generate_app_sign(app_key: str, app_secret: str, open_api_request_time: str) -> str | None:
    """gpt_signature:app_secret 对 {requestTime, appKey, appSecret} 做 HMAC-SHA1。"""
    if app_key is None:
        return None
    params = {
        "openApiRequestTime": str(open_api_request_time),
        "appKey": app_key,
        "appSecret": app_secret,
    }
    query_string = urlencode(params).lower()
    hmac_obj = hmac.new(app_secret.encode("utf-8"), query_string.encode("utf-8"), "sha1")
    return base64.b64encode(hmac_obj.digest()).decode("utf-8")
