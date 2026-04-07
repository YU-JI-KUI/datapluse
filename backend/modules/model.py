"""
预标注模块：调用内部 LLM 平台
use_mock=True  → 随机分配标签（开发用）
use_mock=False → 发 HTTP 请求到内部平台（生产用）

替换真实接口时，只需修改 _call_real_llm() 函数即可
"""
from __future__ import annotations

import random
from typing import Any

import httpx

from config.settings import get_settings


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


async def _call_real_llm(text: str, labels: list[str]) -> tuple[str, float]:
    """
    调用内部大模型平台。
    根据实际平台 API 格式修改此函数。
    """
    settings = get_settings()
    prompt = _build_prompt(text, labels)

    payload = {
        "model": settings.llm_model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 32,
    }

    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        resp = await client.post(
            settings.llm_api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        result = resp.json()

    # 解析返回值 —— 根据实际平台格式调整
    raw_label = result["choices"][0]["message"]["content"].strip()
    # 匹配最接近的标签
    label = raw_label if raw_label in labels else labels[0]
    score = result.get("usage", {}).get("confidence", 0.9)
    return label, float(score)


# ── 公共接口 ───────────────────────────────────────────────────────────────

async def pre_annotate(item: dict[str, Any]) -> dict[str, Any]:
    """对单条数据进行预标注，返回更新后的 item"""
    settings = get_settings()
    labels = settings.labels
    text = item["text"]

    try:
        if settings.llm_use_mock:
            label, score = _mock_predict(text, labels)
        else:
            label, score = await _call_real_llm(text, labels)
    except Exception as e:
        label = labels[0]
        score = 0.0
        item["pre_annotate_error"] = str(e)

    item = dict(item)
    item["model_pred"] = label
    item["model_score"] = score
    item["status"] = "pre_annotated"
    return item


async def pre_annotate_batch(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """批量预标注"""
    results = []
    for item in items:
        results.append(await pre_annotate(item))
    return results
