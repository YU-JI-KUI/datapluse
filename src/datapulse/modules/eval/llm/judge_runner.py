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
    """大模型限流/重试耗尽。上层据此暂停整个评测、退避后再继续，而不是跑成全垃圾。

    partial: 触发限流的那一批里「已成功跑完」的 (sample_idx, judge) 列表。上层据此
    把已完成部分落盘,避免续跑时整批重做。
    """

    def __init__(self, message: str, partial: list | None = None) -> None:
        super().__init__(message)
        self.partial = partial or []


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
        # 输出固定为 11 字段 JSON，几百 token 足够；设上限防偶发话痨撑爆响应/变慢，
        # 又留足空间不截断 JSON（截断会导致解析失败）
        max_tokens=2048,
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


async def judge_batch(samples: list[dict], bu: BUConfig) -> list[dict]:
    """并发跑一批样本,返回与 samples 一一对应的 judge 结果。

    限流熔断:任一 worker 撞限流即置 tripped,尚未开跑的 worker 直接放弃(不再白发
    LLM 请求烧额度);已成功跑完的结果随 RateLimitedError.partial 上抛,供上层落盘,
    续跑时不重做。在途请求无法收回(会自然跑完),但能挡住同批后续大量调用。
    """
    total = len(samples)
    results: list[dict | None] = [None] * total
    sem = asyncio.Semaphore(max(1, settings.judge_concurrency))
    tripped = asyncio.Event()   # 限流熔断标志:置位后未开跑的 worker 跳过

    async def worker(idx: int, s: dict):
        if tripped.is_set():
            return
        async with sem:
            if tripped.is_set():    # 排队期间可能已被熔断,再确认一次
                return
            results[idx] = await judge_one(s, bu)

    # return_exceptions=True:单 worker 非预期异常不中断整批;该位置回填带 _error 占位。
    # judge_one 已把单条失败转成 _error,只有限流会以 RateLimitedError 冒泡到这里。
    outcomes = await asyncio.gather(
        *(_guard(worker(i, s), tripped) for i, s in enumerate(samples)),
        return_exceptions=True,
    )
    if any(isinstance(o, RateLimitedError) for o in outcomes):
        partial = [(i, r) for i, r in enumerate(results) if r is not None]
        raise RateLimitedError("本批触发大模型限流", partial=partial)
    for idx, o in enumerate(outcomes):
        if isinstance(o, Exception) and results[idx] is None:
            results[idx] = {"_error": str(o), "needs_human_review": True}
    return results  # type: ignore[return-value]


async def _guard(coro, tripped: asyncio.Event):
    """跑 worker;遇限流先置熔断标志再上抛,让同批尚未开跑的 worker 尽早放弃。"""
    try:
        return await coro
    except RateLimitedError:
        tripped.set()
        raise


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
