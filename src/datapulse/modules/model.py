"""
预标注模块：调用内部 LLM 平台
use_mock=True  → 随机分配标签，同时生成模拟 COT（开发用）
use_mock=False → 发 HTTP 请求到内部平台（生产用）

配置通过 cfg dict 传入（来自 DB t_system_config），支持热更新。
返回值包含预测结果 (label, score, cot)，不修改 item 状态。
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

# 真实 LLM 调用失败后的最大重试次数与退避基数
_MAX_RETRIES     = 3
_RETRY_BACKOFF_S = 1.0


class PreAnnotateError(Exception):
    """真实 LLM 预标注在重试耗尽后仍失败。

    调用方（step_pre_annotate）捕获后跳过该条数据，保持其 cleaned 状态，
    重跑 pipeline 时会自动重试，避免静默写入默认标签污染数据。
    """

# Mock COT 模板：根据 label/score 生成不同风格的推理描述
_MOCK_COT_TEMPLATES = [
    (
        "分析文本语义特征，识别到与「{label}」高度相关的表达模式。"
        "核心依据：用户语句的意图指向明确，与该类别标准描述匹配度较高。"
        "置信度 {score:.1%}，判定结果可靠。"
    ),
    (
        "对文本进行意图解析：逐步拆解用户输入的关键信息，"
        "对比各候选标签的语义范围，「{label}」与当前文本的语义重叠度最高。"
        "综合评分 {score:.1%}，选定该标签作为预测结果。"
    ),
    (
        "推理步骤：① 提取文本主题词；② 与各意图类别原型进行相似度计算；"
        "③「{label}」类别得分最高（{score:.1%}）；④ 排除其他候选标签后确认结论。"
    ),
    (
        "基于语义匹配算法：输入文本在嵌入空间中与「{label}」类别中心距离最近，"
        "余弦相似度换算置信度约 {score:.1%}。推断该文本表达了{label}类意图。"
    ),
]


def _mock_predict(text: str, labels: list[str]) -> tuple[str, float, str]:
    """Mock 预标注，返回 (label, score, cot)"""
    rng = random.Random(hash(text) % (2**31))
    label   = rng.choice(labels)
    score   = round(rng.uniform(0.65, 0.99), 4)
    # 根据 text hash 选一个 COT 模板，生成差异化的推理描述
    tmpl    = _MOCK_COT_TEMPLATES[hash(text[:16]) % len(_MOCK_COT_TEMPLATES)]
    cot     = tmpl.format(label=label, score=score)
    return label, score, cot


def _build_prompt(text: str, labels: list[str]) -> str:
    labels_str = "、".join(labels)
    return (
        f"请判断以下用户输入属于哪种意图，只从以下标签中选一个：{labels_str}\n"
        f"用户输入：{text}\n"
        f"请先用一两句话说明判断依据（Chain of Thought），再在最后一行只输出标签名称。"
    )


async def _call_real_llm(
    text: str,
    labels: list[str],
    cfg: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> tuple[str, float, str]:
    """调用真实 LLM，返回 (label, score, cot)。

    client 由调用方（step_pre_annotate）创建并在整个 pipeline 运行期间复用，
    避免每条数据一次 TCP+TLS 握手（6 万条 = 6 万次握手）。
    失败自动重试 _MAX_RETRIES 次（线性退避），耗尽后抛 PreAnnotateError。
    """
    llm_cfg    = cfg.get("llm", {})
    api_url    = llm_cfg.get("api_url", "")
    model_name = llm_cfg.get("model_name", "")
    timeout    = llm_cfg.get("timeout", 30)

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": _build_prompt(text, labels)}],
        "temperature": 0.1,
        "max_tokens": 256,
    }
    headers = {"Content-Type": "application/json"}

    last_err: Exception | None = None
    result = None
    for attempt in range(_MAX_RETRIES):
        try:
            if client is not None:
                resp = await client.post(api_url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=timeout) as own_client:
                    resp = await own_client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            break
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_BACKOFF_S * (attempt + 1))
    if result is None:
        raise PreAnnotateError(
            f"LLM 调用失败（已重试 {_MAX_RETRIES} 次）: {last_err}"
        ) from last_err

    content   = result["choices"][0]["message"]["content"].strip()
    lines     = [ln.strip() for ln in content.splitlines() if ln.strip()]
    raw_label = lines[-1] if lines else ""
    label     = raw_label if raw_label in labels else labels[0]
    score     = float(result.get("usage", {}).get("confidence", 0.9))
    # COT = 最后一行之前的所有内容
    cot       = "\n".join(lines[:-1]) if len(lines) > 1 else ""
    return label, score, cot


async def pre_annotate(
    item: dict[str, Any],
    cfg: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> tuple[str, float, str]:
    """对单条数据预标注，返回 (label, score, cot)。

    真实 LLM 失败重试耗尽后抛 PreAnnotateError（不再静默返回默认标签），
    由调用方决定跳过该条并保持 cleaned 状态待重跑。
    """
    llm_cfg  = cfg.get("llm", {})
    use_mock = llm_cfg.get("use_mock", True)
    labels   = cfg.get("labels", ["意图A", "意图B"])
    text     = item.get("content", "")

    if use_mock:
        return _mock_predict(text, labels)
    return await _call_real_llm(text, labels, cfg, client=client)
