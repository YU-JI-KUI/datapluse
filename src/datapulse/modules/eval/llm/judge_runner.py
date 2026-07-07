"""Judge 调度入口:按配置选 mock / pingan,对外暴露统一的 async 接口。

service 层只认 judge_one(sample) -> dict,不关心底层用谁。
"""
from __future__ import annotations

import asyncio
import logging

from datapulse.modules.eval._settings import settings
from datapulse.modules.eval.advisor import (
    build_card_prompts,
    rule_based_cards,
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


class EvalCancelled(Exception):
    """评测中途发现任务已被删除（DB 记录不存在）。上层据此干净中止、释放串行锁，
    什么都不写（记录已没了）。让删除运行中任务后新任务能立即接管。"""


class EvalPaused(Exception):
    """评测中途发现任务被手动暂停（status=paused）。上层据此中止、释放锁、保留已落盘
    进度，不覆盖状态、不自动续跑，等用户手动恢复。"""


# 输出是 11 字段 JSON，每个结论前还带一句依据，复杂 case 偏长；3072 留足空间不被
# 截断（截断会导致 JSON 不闭合、解析失败）。
_JUDGE_MAX_TOKENS = 3072
# 解析失败时的升温重试：temp=0 是确定性的，重试只会得到同样的坏输出，必须升温打破。
# 换 seed 进一步增加多样性。约 1% 偶发坏 JSON 经此一次重试绝大多数能救回。
_RETRY_TEMPERATURE = 0.3
_RETRY_SEED = 1234


async def _call_judge(messages: list, temperature: float, seed: int) -> str:
    """调一次模型并取出文本内容。限流向上抛，其余异常交给调用方。"""
    resp = await call_bigmodel_api(
        query=messages,
        scene_id=settings.llm_scene_id,
        app_key=settings.llm_app_key,
        app_secret=settings.llm_app_secret,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        response_format={"type": "json_object"},
        max_tokens=_JUDGE_MAX_TOKENS,
        temperature=temperature,
        seed=seed,
    )
    if isinstance(resp, dict) and resp.get("rate_limited"):
        # 重试后仍被限流 → 抛限流信号，让上层暂停评测（区别于「单条脏格式」）
        raise RateLimitedError(resp.get("error", "rate limited"))
    return extract_content(resp)


async def _judge_strong(sample: dict, bu: BUConfig) -> dict:
    """调强模型(平安大模型)做精判。

    首跑 temp=0(确定性、可复现);若模型偶发吐出非法 JSON(约 1%),升温换 seed
    重试一次再解析。限流不在这里重试(由 call_bigmodel_api 内部退避 + 上层暂停)。
    """
    messages = build_messages(sample, bu)
    row = sample.get("row_index")

    content = await _call_judge(messages, temperature=0.0, seed=42)
    logger.debug("模型原始返回 row=%s: %s", row, content)
    try:
        return parse_judge_output(content)
    except ValueError as e:
        # 坏 JSON：升温重试一次。temp=0 重试无意义,必须升温打破确定性死循环。
        logger.warning("judge 输出非法 JSON,升温重试 row=%s: %s", row, e)
        content = await _call_judge(messages, temperature=_RETRY_TEMPERATURE, seed=_RETRY_SEED)
        logger.debug("模型重试返回 row=%s: %s", row, content)
        return parse_judge_output(content)   # 仍失败则抛 ValueError,由 judge_one 转 _error


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


async def _call_advice(messages: list) -> str:
    """调一次模型生成一张建议卡（纯文本 markdown，不强制 JSON、输出上限更小）。"""
    resp = await call_bigmodel_api(
        query=messages,
        scene_id=settings.llm_scene_id,
        app_key=settings.llm_app_key,
        app_secret=settings.llm_app_secret,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        max_tokens=settings.advice_max_tokens,
    )
    if isinstance(resp, dict) and resp.get("rate_limited"):
        raise RateLimitedError(resp.get("error", "rate limited"))
    return extract_content(resp)


async def generate_advice(facts: dict, insights: dict, bu: BUConfig,
                          bu_dispatch: dict | None = None) -> dict:
    """生成优化建议（多专项卡片）。每张卡各调一次模型出一段纯文本 markdown。

    卡片体系：固定 3（分发/解决率/新分类）+ 动态 2N（每分类·分发/解决率）。
    并发受 judge_concurrency 节流；单卡失败跳过、warning；全败或非 pingan 后端整体
    降级到规则版卡片。返回 {"source": "model"|"rule", "cards": [...]}。
    """
    specs = build_card_prompts(facts, insights, bu, bu_dispatch)

    # 非真实模型 / 无料 → 直接规则版（mock 也走这，保证离线端到端可验）
    if active_backend() != "pingan" or not specs:
        return {"source": "rule", "cards": rule_based_cards(facts, insights, bu, bu_dispatch)}

    sem = asyncio.Semaphore(max(1, settings.judge_concurrency))

    async def one(spec: dict) -> dict | None:
        async with sem:
            try:
                text = await _call_advice(spec["messages"])
            except Exception as e:  # 单卡失败跳过，不拖累其余卡
                logger.warning("建议卡生成失败,跳过 id=%s: %s", spec["id"], e)
                return None
            if not (text or "").strip():
                return None
            return {"id": spec["id"], "title": spec["title"],
                    "dimension": spec["dimension"], "category": spec["category"],
                    "text": text.strip()}

    results = await asyncio.gather(*(one(s) for s in specs))
    cards = [c for c in results if c]
    if cards:
        return {"source": "model", "cards": cards}
    # 全败：整体降级规则版
    logger.error("全部建议卡生成失败,降级到规则版")
    return {"source": "rule", "cards": rule_based_cards(facts, insights, bu, bu_dispatch)}
