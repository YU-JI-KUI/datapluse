"""平安大模型平台(Qwen3 等)API 客户端。

搬自 ark_navigator 的 llm_platform_client,去掉 Ray 相关耦合,保留双签名鉴权 +
指数退避重试的核心逻辑。只负责调用平安大模型 OpenAI 接口。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx

from datapulse.modules.eval._settings import settings
from datapulse.modules.eval.llm.signature import generate_app_sign, get_open_api_sign

logger = logging.getLogger(__name__)

# AsyncClient 的连接池绑定在「创建它的事件循环」上,不能跨循环复用。
# 评测 worker 每个任务用独立 asyncio.run() 起新循环跑完即关,若全进程共用一个
# client,第二个任务就会在已关闭的旧循环上发请求 → RuntimeError: Event loop is closed,
# 整个任务的 LLM 调用全失败。故按当前 running loop 各缓存一个 client。
_clients: dict[int, httpx.AsyncClient] = {}


def _get_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    key = id(loop)
    client = _clients.get(key)
    if client is None:
        client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            timeout=httpx.Timeout(60.0, connect=10.0),
            http2=False,
        )
        _clients[key] = client
    return client


async def close_client() -> None:
    """关闭并丢弃当前事件循环的 client（任务跑完时由编排层调用，释放连接池）。

    必须在持有该 client 的同一个循环里调用（aclose 是 async）。其它循环的 client
    各自负责，不在这里碰。
    """
    loop = asyncio.get_running_loop()
    client = _clients.pop(id(loop), None)
    if client is not None:
        await client.aclose()


async def call_bigmodel_api(
    query: str | list,
    scene_id: str,
    app_key: str,
    app_secret: str,
    timeout: int = 30,
    max_retries: int = 5,
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
    # 调用前打完整 request payload（仅 DEBUG）。isEnabledFor 守卫避免非 DEBUG 时白做 json 序列化
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("大模型请求 payload request_id=%s: %s",
                     request_id, json.dumps(payload, ensure_ascii=False))

    # 可重试的 HTTP 状态：429 限流 + 5xx 网关/服务端暂时性故障
    retryable_status = {429, 500, 502, 503, 504}

    async def _backoff(attempt: int, retry_after: float | None) -> None:
        # 限流优先用服务端 Retry-After，否则指数退避（带上限，避免等太久）。
        # 必须 asyncio.sleep，time.sleep 会卡住整个 event loop。
        delay = retry_after if retry_after else min(2 ** attempt, 30)
        await asyncio.sleep(delay)

    for attempt in range(max_retries):
        last_err = ""
        rate_limited = False
        try:
            response = await _get_client().post(
                url=settings.open_ai_url, headers=headers, json=payload, timeout=timeout,
            )
            if response.status_code == 200:
                return response.json()
            # 限流 / 暂时性故障 → 退避重试
            if response.status_code in retryable_status:
                rate_limited = response.status_code == 429
                ra = response.headers.get("Retry-After")
                retry_after = float(ra) if ra and ra.replace(".", "").isdigit() else None
                last_err = f"HTTP {response.status_code}"
                logger.warning("大模型可重试错误 %s (attempt %d/%d, 限流=%s)",
                               last_err, attempt + 1, max_retries, rate_limited)
                if attempt < max_retries - 1:
                    await _backoff(attempt, retry_after)
                    continue
                return {"error": f"{last_err}，已重试 {max_retries} 次", "rate_limited": rate_limited}
            # 其它 4xx：不可重试，直接失败（鉴权/参数错误，重试也没用）
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            # 网络层错误（连接失败/超时）→ 退避重试
            last_err = str(e)
            logger.warning("大模型网络错误 (attempt %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                await _backoff(attempt, None)
                continue
            return {"error": f"网络失败，已重试 {max_retries} 次: {e}"}
        except Exception as e:  # noqa: BLE001  解析/不可重试错误
            logger.error("大模型调用失败（不可重试）: %s", e)
            return {"error": str(e)}
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
