"""Judge 调度入口:按配置选 mock / pingan,对外暴露统一的 async 接口。

service 层只认 judge_one(sample) -> dict,不关心底层用谁。
"""
from __future__ import annotations

import asyncio
import logging

from datapulse.modules.eval._settings import settings
from datapulse.modules.eval.advisor import (
    build_advice_prompt,
    parse_advice,
    rule_based_advice,
)
from datapulse.modules.eval.bu.base import BUConfig
from datapulse.modules.eval.judge import build_messages, parse_judge_output
from datapulse.modules.eval.llm.mock_judge import mock_judge
from datapulse.modules.eval.llm.pingan_client import call_bigmodel_api, extract_content

logger = logging.getLogger(__name__)


def active_backend() -> str:
    """返回当前实际生效的后端。配置 pingan 但变量不全时降级到 mock。"""
    if settings.judge_backend == "pingan" and settings.pingan_ready():
        return "pingan"
    return "mock"


class RateLimitedError(Exception):
    """大模型限流/重试耗尽。上层据此暂停整个评测、退避后再继续，而不是跑成全垃圾。"""


async def _judge_strong(sample: dict, bu: BUConfig) -> dict:
    """调强模型(平安大模型)做精判。"""
    messages = build_messages(sample, bu)
    resp = await call_bigmodel_api(
        query=messages,
        scene_id=settings.llm_scene_id,
        app_key=settings.llm_app_key,
        app_secret=settings.llm_app_secret,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        response_format={"type": "json_object"},
    )
    # 重试后仍被限流 → 抛限流信号，让上层暂停评测（区别于「单条脏格式」）
    if isinstance(resp, dict) and resp.get("rate_limited"):
        raise RateLimitedError(resp.get("error", "rate limited"))
    content = extract_content(resp)
    logger.debug("模型原始返回 row=%s: %s", sample.get("row_index"), content)
    return parse_judge_output(content)


async def judge_one(sample: dict, bu: BUConfig) -> dict:
    """对单条样本跑 Judge,返回结构化结果。失败时返回带 _error 的结果。

    限流异常向上抛（整批暂停）；其它单条失败补 _error，不中断整批。
    """
    try:
        if active_backend() == "pingan":
            return await _judge_strong(sample, bu)
        return mock_judge(sample, bu)
    except RateLimitedError:
        raise   # 限流信号必须上抛，由评测引擎暂停处理
    except Exception as e:  # 单条失败不应中断整批
        logger.error("judge 单条失败 row=%s: %s", sample.get("row_index"), e)
        return {"_error": str(e), "needs_human_review": True}


async def judge_batch(samples: list[dict], bu: BUConfig, on_progress=None) -> list[dict]:
    """并发跑一批样本。on_progress(done, total) 回调用于上报进度。"""
    total = len(samples)
    results: list[dict | None] = [None] * total
    sem = asyncio.Semaphore(max(1, settings.judge_concurrency))
    done = 0
    lock = asyncio.Lock()

    async def worker(idx: int, s: dict):
        nonlocal done
        async with sem:
            results[idx] = await judge_one(s, bu)
        async with lock:
            done += 1
            if on_progress:
                on_progress(done, total)

    # return_exceptions=True:即便某 worker 抛出非预期异常,也不中断整批;
    # 该位置的结果回填为带 _error 的占位,保证 results 与 samples 一一对应。
    outcomes = await asyncio.gather(
        *(worker(i, s) for i, s in enumerate(samples)),
        return_exceptions=True,
    )
    # 本批出现限流 → 整批上抛，让评测引擎暂停（已完成的批已落盘，不重做）
    if any(isinstance(o, RateLimitedError) for o in outcomes):
        raise RateLimitedError("本批触发大模型限流")
    for idx, o in enumerate(outcomes):
        if isinstance(o, Exception) and results[idx] is None:
            results[idx] = {"_error": str(o), "needs_human_review": True}
    return results  # type: ignore[return-value]


async def generate_advice(insights: dict, bu: BUConfig, bu_dispatch: dict | None = None) -> dict:
    """生成优化建议。走真实模型则让模型读聚合指标给建议,否则用规则兜底。

    返回 {"source": "model"|"rule", "items": [...]}。模型失败自动降级到规则。
    """
    if active_backend() == "pingan":
        try:
            messages = build_advice_prompt(insights, bu, bu_dispatch)
            resp = await call_bigmodel_api(
                query=messages,
                scene_id=settings.llm_scene_id,
                app_key=settings.llm_app_key,
                app_secret=settings.llm_app_secret,
                timeout=settings.llm_timeout,
                max_retries=settings.llm_max_retries,
            )
            items = parse_advice(extract_content(resp))
            if items:
                return {"source": "model", "items": items}
        except Exception as e:
            logger.error("模型生成建议失败,降级到规则: %s", e)
    return {"source": "rule", "items": rule_based_advice(insights, bu_dispatch)}
