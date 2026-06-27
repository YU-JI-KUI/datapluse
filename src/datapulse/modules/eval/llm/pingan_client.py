"""平安大模型平台(Qwen3 等)API 客户端。

搬自 ark_navigator 的 llm_platform_client,去掉 Ray 相关耦合,保留双签名鉴权 +
指数退避重试的核心逻辑。只负责调用平安大模型 OpenAI 接口。
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

import httpx

from datapulse.modules.eval._settings import settings
from datapulse.modules.eval.llm.signature import generate_app_sign, get_open_api_sign

logger = logging.getLogger(__name__)

# 进程内复用一个 AsyncClient(禁 keep-alive 复杂度,够用即可)
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            timeout=httpx.Timeout(60.0, connect=10.0),
            http2=False,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def call_bigmodel_api(
    query: str | list,
    scene_id: str,
    app_key: str,
    app_secret: str,
    timeout: int = 30,
    max_retries: int = 3,
    **kwargs,
) -> dict[Any, Any] | None:
    """调用平安大模型服务接口。

    Args:
        query: 字符串(自动包成 user message)或完整 messages list
        scene_id: 业务场景 ID
        app_key / app_secret: 应用 key/secret(用于 HMAC 签名)
        timeout: 单次请求超时(秒)
        max_retries: 最大重试次数
    Returns:
        API 响应 JSON;失败返回 {"error": "..."} 或 None
    """
    request_timestamp = str(int(time.time() * 1000))
    open_api_signature = get_open_api_sign(settings.rsa_pk, request_timestamp)
    gpt_signature = generate_app_sign(app_key, app_secret, request_timestamp)

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "openApiCode": settings.open_api_code,
        "openApiCredential": settings.cre_id,
        "openApiRequestTime": request_timestamp,
        "openApiSignature": open_api_signature,
        "gpt_app_key": app_key,
        "gpt_signature": gpt_signature,
    }
    request_id = str(uuid.uuid4())
    messages = query if isinstance(query, list) else [{"role": "user", "content": query}]
    payload = {
        "request_id": request_id,
        "messages": messages,
        "stream": False,
        "scene_id": scene_id,
        "seed": 42,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
        **kwargs,
    }
    logger.info("调用大模型 request_id=%s scene_id=%s", request_id, scene_id)

    for attempt in range(max_retries):
        try:
            try:
                response = await _get_client().post(
                    url=settings.open_ai_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()
            except httpx.RequestError:
                # 网络层错误抛给外层做指数退避
                raise
            except Exception as e:  # 非网络错误(如 4xx/5xx)
                logger.error("大模型调用失败: %s", e)
                if attempt < max_retries - 1:
                    continue
                return {"error": str(e)}
        except httpx.RequestError as e:
            logger.warning("第 %d 次请求失败: %s", attempt + 1, e)
            if attempt < max_retries - 1:
                # 必须 asyncio.sleep,time.sleep 会卡住整个 event loop
                await asyncio.sleep(1 * (2 ** attempt))
            else:
                # 返回带 error 的 dict 而非 None,保留「网络失败」信息,
                # 便于上层与「JSON 解析失败」区分排查
                return {"error": f"网络失败,已重试 {max_retries} 次: {e}"}
    return {"error": "未知失败"}


def extract_content(resp: dict | None) -> str:
    """从平安大模型响应里抽出文本内容,兼容 OpenAI 风格与若干变体。"""
    if not resp or not isinstance(resp, dict):
        raise ValueError("空响应或非法响应")
    if "error" in resp:
        raise ValueError(f"模型返回错误: {resp['error']}")
    # OpenAI 风格:choices[0].message.content
    choices = resp.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content:
            return content
        # 个别实现把内容放 text
        if choices[0].get("text"):
            return choices[0]["text"]
    # 兜底:常见自定义字段
    for k in ("data", "result", "content", "answer"):
        v = resp.get(k)
        if isinstance(v, str) and v.strip():
            return v
    raise ValueError(f"无法从响应中抽取内容: {list(resp.keys())}")
