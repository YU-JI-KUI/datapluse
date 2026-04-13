"""
预标注模块：调用内部 LLM 平台
use_mock=True  → 随机分配标签（开发用）
use_mock=False → 发 HTTP 请求到内部平台（生产用）

配置通过 cfg dict 传入（来自 DB t_system_config），支持热更新。
返回值仅包含预测结果（label + score），不修改 item 状态。
"""

from __future__ import annotations

import random
from typing import Any

import httpx


def _mock_predict(text: str, labels: list[str]) -> tuple[str, float]:
    random.seed(hash(text) % (2**31))
    label = random.choice(labels)
    score = round(random.uniform(0.65, 0.99), 4)
    return label, score


def _build_prompt(text: str, labels: list[str]) -> str:
    labels_str = "、".join(labels)
    return (
        f"请判断以下用户输入属于哪种意图，只从以下标签中选一个：{labels_str}\n"
        f"用户输入：{text}\n"
        f"请直接返回标签名称，不要解释。"
    )


async def _call_real_llm(text: str, labels: list[str], cfg: dict[str, Any]) -> tuple[str, float]:
    llm_cfg = cfg.get("llm", {})
    api_url    = llm_cfg.get("api_url", "")
    model_name = llm_cfg.get("model_name", "")
    timeout    = llm_cfg.get("timeout", 30)

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": _build_prompt(text, labels)}],
        "temperature": 0.1,
        "max_tokens": 32,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(api_url, json=payload,
                                 headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        result = resp.json()

    raw_label = result["choices"][0]["message"]["content"].strip()
    label = raw_label if raw_label in labels else labels[0]
    score = float(result.get("usage", {}).get("confidence", 0.9))
    return label, score


async def pre_annotate(item: dict[str, Any], cfg: dict[str, Any]) -> tuple[str, float]:
    """对单条数据预标注，返回 (label, score)"""
    llm_cfg  = cfg.get("llm", {})
    use_mock = llm_cfg.get("use_mock", True)
    labels   = cfg.get("labels", ["意图A", "意图B"])
    text     = item.get("content", "")

    try:
        if use_mock:
            return _mock_predict(text, labels)
        return await _call_real_llm(text, labels, cfg)
    except Exception:
        return labels[0], 0.0


async def pre_annotate_batch(
    items: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> list[tuple[dict[str, Any], str, float]]:
    """批量预标注，返回 [(item, label, score), ...]"""
    results = []
    for item in items:
        label, score = await pre_annotate(item, cfg)
        results.append((item, label, score))
    return results
