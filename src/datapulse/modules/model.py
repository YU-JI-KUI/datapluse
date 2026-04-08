"""
预标注模块：调用内部 LLM 平台
use_mock=True  → 随机分配标签（开发用）
use_mock=False → 发 HTTP 请求到内部平台（生产用）

配置通过 cfg dict 传入（来自 DB system_config），支持热更新。
替换真实接口时，只需修改 _call_real_llm() 函数即可。
"""

from __future__ import annotations

import random
from typing import Any

import httpx

# ── Mock 实现 ──────────────────────────────────────────────────────────────


def _mock_predict(text: str, labels: list[str]) -> tuple[str, float]:
    """随机预标注，用于开发和演示"""
    random.seed(hash(text) % (2**31))
    label = random.choice(labels)
    score = round(random.uniform(0.65, 0.99), 4)
    return label, score


# ── 真实 LLM 接口（预留）──────────────────────────────────────────────────


def _build_prompt(text: str, labels: list[str]) -> str:
    labels_str = "、".join(labels)
    return (
        f"请判断以下用户输入属于哪种意图，只从以下标签中选一个：{labels_str}\n"
        f"用户输入：{text}\n"
        f"请直接返回标签名称，不要解释。"
    )


async def _call_real_llm(text: str, labels: list[str], cfg: dict[str, Any]) -> tuple[str, float]:
    """
    调用内部大模型平台。
    根据实际平台 API 格式修改此函数。
    cfg 来自 DB system_config.llm 节点。
    """
    llm_cfg = cfg.get("llm", {})
    api_url = llm_cfg.get("api_url", "")
    model_name = llm_cfg.get("model_name", "")
    timeout = llm_cfg.get("timeout", 30)

    prompt = _build_prompt(text, labels)
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 32,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        result = resp.json()

    raw_label = result["choices"][0]["message"]["content"].strip()
    label = raw_label if raw_label in labels else labels[0]
    score = result.get("usage", {}).get("confidence", 0.9)
    return label, float(score)


# ── 公共接口 ───────────────────────────────────────────────────────────────


async def pre_annotate(item: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """对单条数据进行预标注，返回更新后的 item"""
    llm_cfg = cfg.get("llm", {})
    use_mock = llm_cfg.get("use_mock", True)
    labels = cfg.get("labels", ["意图A", "意图B"])
    text = item["text"]

    try:
        if use_mock:
            label, score = _mock_predict(text, labels)
        else:
            label, score = await _call_real_llm(text, labels, cfg)
    except Exception as e:
        label = labels[0]
        score = 0.0
        item = dict(item)
        item["pre_annotate_error"] = str(e)

    item = dict(item)
    item["model_pred"] = label
    item["model_score"] = score
    item["status"] = "pre_annotated"
    return item


async def pre_annotate_batch(
    items: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """批量预标注"""
    results = []
    for item in items:
        results.append(await pre_annotate(item, cfg))
    return results
