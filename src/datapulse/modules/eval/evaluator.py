"""评测编排器:把 pipeline + judge + 指标/洞察 串成一次完整评测。

两种模式(由数据是否带二值金标自动判定):
  - calibration:有人工金标 → 额外算 κ/F1/混淆矩阵,证明 Judge 可信(低频)
  - production :无金标(如每天 3万行原始日志)→ 直接出评测结论 + 业务洞察(高频)

产出对象供 API/前端消费:summary / filter_stats / mode / metrics(仅校准) /
intent_distribution / insights(业务洞察) / rows / disagreements。
"""
from __future__ import annotations

from collections import Counter, defaultdict

from datapulse.modules.eval import _store as store
from datapulse.modules.eval.bu.base import BUConfig
from datapulse.modules.eval.llm.judge_runner import (
    RateLimitedError,
    active_backend,
    generate_advice,
    judge_batch,
)
from datapulse.modules.eval.metrics import binary_report
from datapulse.modules.eval.pipeline import build_all_samples, detect_gold, load_and_prep


def _resolved_to_binary(judge: dict) -> str:
    """answer_resolved(yes/partial/no/unknown)归一成「是/否」与金标对齐。"""
    if not isinstance(judge, dict) or "_error" in judge:
        return ""
    return "是" if judge.get("answer_resolved") == "yes" else "否"


def _dispatch_correct(sample: dict, judge: dict) -> bool | None:
    """BU 分发是否正确 = LLM 判「该不该本BU承接」与日志事实「分发BU是否=本BU」一致。

    返回 True/False;judge 出错或缺字段返回 None(不计入统计)。
    """
    if not isinstance(judge, dict) or "_error" in judge or "should_dispatch_to_bu" not in judge:
        return None
    return bool(judge["should_dispatch_to_bu"]) == bool(sample.get("dispatched_to_bu"))


# 非业务分类的占位值:模型对"不该本BU承接"的样本填这些,不算真实业务分类,
# 统计切片时归为空(落到「(未分类)」),不污染各业务类型的解决率。
_NON_BUSINESS_TYPES = {"非本BU", "拒识", "其他", ""}


def _business_type(judge: dict) -> str:
    """取模型返回的业务分类标签(字段名 business_type)。非业务分类占位值归空。"""
    if not isinstance(judge, dict):
        return ""
    bt = (judge.get("business_type") or "").strip()
    return "" if bt in _NON_BUSINESS_TYPES else bt


def _dispatch_scene(sample: dict, judge: dict) -> str:
    """按四象限给 BU 分发结果打场景标签(用 AI 判断 vs Excel 实际两个原始事实)。

    should=AI 认为该不该本BU承接;actual=Excel 实际是否分给本BU。
      正常    : should==actual(都该且分了 / 都不该且没分)
      该拒未拒: 不该本BU接,却被分进来了(should=F, actual=T)
      该分未分: 该本BU接,却没分进来(should=T, actual=F)
    judge 出错/缺字段返回空串(不参与统计)。
    """
    if not isinstance(judge, dict) or "_error" in judge or "should_dispatch_to_bu" not in judge:
        return ""
    should = bool(judge["should_dispatch_to_bu"])
    actual = bool(sample.get("dispatched_to_bu"))
    if should == actual:
        return "正常"
    return "该拒未拒" if (actual and not should) else "该分未分"


def assemble_row(sample: dict, judge: dict) -> dict:
    """把一条样本 + judge 输出组装成明细行(抽出复用,供续跑场景也能调)。"""
    gold = sample["gold"]
    dispatch_correct = _dispatch_correct(sample, judge)
    j_dispatch = "" if dispatch_correct is None else ("是" if dispatch_correct else "否")
    j_resolved = _resolved_to_binary(judge)
    row = {
        "row_index": sample["row_index"],
        "session": sample["session"],
        "turn": sample["turn"],
        "question": sample["question"],
        "context": sample["context"],  # [{turn, user, ai}, ...] 含前文 AI 回答
        "next_user_turn": sample["next_user_turn"],
        "dispatched_intent": sample["dispatched_intent"],
        "dispatched_bu": sample.get("dispatched_bu", ""),       # Excel「分发BU」列原值
        "dispatched_to_bu": sample.get("dispatched_to_bu", False),
        "answer_text": sample["answer_text"],
        "judge": judge,
        "j_intent": _business_type(judge),
        "dispatch_correct": dispatch_correct,
        "dispatch_scene": _dispatch_scene(sample, judge),  # 正常/该拒未拒/该分未分
        "j_dispatch": j_dispatch,
        "j_resolved": j_resolved,
        "j_resolved_raw": judge.get("answer_resolved", "") if isinstance(judge, dict) else "",
        "gold": gold,
        "disagree_dispatch": gold["dispatch"] in ("是", "否") and gold["dispatch"] != j_dispatch,
        "disagree_resolved": gold["resolved"] in ("是", "否") and gold["resolved"] != j_resolved,
    }
    row["is_disagreement"] = row["disagree_dispatch"] or row["disagree_resolved"]
    return row


# 不一致 case / 未解决样例只保留有限条数:百万级下全量驻留会 OOM,
# 报表/导出只需代表性样本,完整逐条已落盘 t_eval_task_row,可分页查。
_MAX_DISAGREEMENTS = 500
_MAX_UNRESOLVED_EXAMPLES = 3

# 二值校准维度规格(与纯函数版本保持一致):分发是否正确 + 答案是否解决
_METRIC_SPECS = (
    ("分发是否正确", "dispatch", "j_dispatch"),
    ("答案是否解决客户问题", "resolved", "j_resolved"),
)


class _IntentSlice:
    """单个业务分类切片的增量计数(对齐 compute_insights.slice_stats)。"""
    __slots__ = ("count", "in_bu", "resolved_yes", "need_review", "examples")

    def __init__(self) -> None:
        self.count = 0
        self.in_bu = 0
        self.resolved_yes = 0
        self.need_review = 0
        self.examples: list[str] = []   # 进漏斗且未解决的典型问题，最多留 N 条


class _StreamAggregator:
    """流式聚合:逐批吃 rows、更新计数,跑完即丢弃 row 本体,不全量驻留内存。

    生产路径只走本类(逐批喂、不全量驻留)。文件末尾的纯函数(compute_insights /
    _bu_dispatch_stats / _intent_distribution / _compute_metrics)不在生产调用,仅供
    tests/eval/test_stream_aggregator.py 做「全量算 == 增量算」的等价校验,是本类的
    正确性 oracle。改本类口径时,纯函数必须同步改,否则等价测试会失败(这正是它们的用途)。
    """

    def __init__(self) -> None:
        self.total = 0
        self.intent_dist: Counter = Counter()             # j_intent 分布
        self.slices: dict[str, _IntentSlice] = defaultdict(_IntentSlice)  # 按 j_intent 切片
        # overall 漏斗(分母 = 分发到本BU)
        self.in_bu_total = 0
        self.resolved_yes_total = 0
        # BU 分发漏斗
        self.disp_scored = 0
        self.disp_correct = 0
        self.disp_miss = 0
        self.disp_over = 0
        # 校准指标:每个维度 4 种「是/否」配对的计数 {(gold, pred): n}
        self.metric_pairs: dict[str, Counter] = {spec[1]: Counter() for spec in _METRIC_SPECS}
        # summary 计数
        self.needs_review = 0
        self.errors = 0
        self.disagreement_count = 0
        self.disagreements: list[dict] = []   # 仅留前 _MAX_DISAGREEMENTS 条

    def update(self, rows: list[dict]) -> None:
        for r in rows:
            self.total += 1
            judge = r["judge"]
            is_judge_dict = isinstance(judge, dict)

            intent = r["j_intent"]
            if intent:
                self.intent_dist[intent] += 1

            # 切片(未分类归入 "(未分类)"，与 compute_insights 一致)
            sl = self.slices[intent or "(未分类)"]
            sl.count += 1
            in_bu = bool(r.get("dispatched_to_bu"))
            need_review = is_judge_dict and judge.get("needs_human_review")
            if need_review:
                sl.need_review += 1
            if in_bu:
                sl.in_bu += 1
                self.in_bu_total += 1
                raw = r["j_resolved_raw"]
                if raw == "yes":
                    sl.resolved_yes += 1
                    self.resolved_yes_total += 1
                elif raw in ("no", "partial") and len(sl.examples) < _MAX_UNRESOLVED_EXAMPLES:
                    sl.examples.append(r["question"])

            # BU 分发漏斗
            dc = r.get("dispatch_correct")
            if dc is not None:
                self.disp_scored += 1
                should = bool(judge.get("should_dispatch_to_bu")) if is_judge_dict else False
                if dc:
                    self.disp_correct += 1
                elif should and not in_bu:
                    self.disp_miss += 1
                elif not should and in_bu:
                    self.disp_over += 1

            # 校准配对计数
            for _name, gold_key, j_key in _METRIC_SPECS:
                gv = r["gold"].get(gold_key, "")
                jv = r.get(j_key, "")
                if gv in ("是", "否") and jv in ("是", "否"):
                    self.metric_pairs[gold_key][(gv, jv)] += 1

            # summary 计数
            if need_review:
                self.needs_review += 1
            if is_judge_dict and "_error" in judge:
                self.errors += 1
            if r["is_disagreement"]:
                self.disagreement_count += 1
                if len(self.disagreements) < _MAX_DISAGREEMENTS:
                    self.disagreements.append(r)

    # ── finalize:产出与纯函数等价的结构 ──────────────────────────────────────

    def intent_distribution(self) -> dict:
        return {"by_intent": [{"name": k, "count": v} for k, v in self.intent_dist.most_common()]}

    def insights(self) -> dict:
        intent_slices = sorted(
            (
                {
                    "name": name,
                    "count": sl.count,
                    "in_bu_count": sl.in_bu,
                    "resolved_rate": _rate(sl.resolved_yes, sl.in_bu),
                    "needs_review_rate": _rate(sl.need_review, sl.count),
                    "unresolved_examples": sl.examples,
                }
                for name, sl in self.slices.items()
            ),
            key=lambda x: x["count"], reverse=True,
        )
        return {
            "overall": {
                "count": self.total,
                "in_bu_count": self.in_bu_total,
                "resolved_rate": _rate(self.resolved_yes_total, self.in_bu_total),
                "dispatch_accuracy": _rate(self.disp_correct, self.disp_scored),
            },
            "by_intent": intent_slices,
        }

    def bu_dispatch(self) -> dict:
        scored = self.disp_scored
        return {
            "scored": scored,
            "correct": self.disp_correct,
            "wrong": scored - self.disp_correct,
            "accuracy": round(self.disp_correct / scored, 4) if scored else 0.0,
            "miss_should_accept_but_rejected": self.disp_miss,
            "over_should_reject_but_accepted": self.disp_over,
        }

    def metrics(self) -> list[dict]:
        """从 4 种配对计数重建指标。等价于全量 y_true/y_pred 喂 binary_report。"""
        out = []
        for name, gold_key, _j_key in _METRIC_SPECS:
            pairs = self.metric_pairs[gold_key]
            if not pairs:
                continue
            y_true = ["是", "是", "否", "否"]
            y_pred = ["是", "否", "是", "否"]
            weights = [pairs.get((t, p), 0) for t, p in zip(y_true, y_pred)]
            if sum(weights) == 0:
                continue
            out.append(binary_report(name, y_true, y_pred, sample_weight=weights))
        return out


async def _judge_streaming(samples, bu, on_progress, task_id, persist, agg: _StreamAggregator) -> None:
    """跑 judge,逐批喂累加器并落盘,不全量收集 rows(百万级避免 OOM)。

    续跑:已落盘的行分批读回喂累加器(喂完即弃),再只对未完成样本跑 judge。
    落盘:分批写入,避免大批量跑一半中断后全部重来。
    """
    total = len(samples)
    done_idx: set[int] = set()
    if persist and task_id:
        done_idx = store.done_row_indices(task_id)
        # 已落盘行分批读回喂累加器,不一次性全部驻留
        for cached_batch in store.iter_rows(task_id, batch_size=1000):
            agg.update(cached_batch)

    pending = [s for s in samples if s["row_index"] not in done_idx]
    done_count = len(done_idx)
    if on_progress:
        on_progress("judging", done_count, total)

    # 批大小 = 并发窗口 + 落盘/进度上报粒度。整批跑完才落盘,所以它也是「崩溃后最多
    # 重跑多少条」的上界:50 条一批,挂了最多重做 49 条(原 200 会白跑近 200 条)。
    # 50 > judge_concurrency(并发 10)能喂满并发,不损吞吐;LLM 调用是瓶颈,多几次
    # 落盘(5万条约 1000 次)代价远小于省下的重复 LLM 调用。
    batch_size = 50
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        try:
            judges = await judge_batch(batch, bu)
        except RateLimitedError as e:
            # 限流:把这批已成功跑完的部分先落盘(不喂累加器——累加器会在续跑读回时
            # 重建),再上抛让引擎暂停退避。续跑时这些行已在库,不重做。
            if persist and task_id and e.partial:
                done_rows = [assemble_row(batch[i], j) for i, j in e.partial]
                store.save_rows(task_id, done_rows)
            raise
        batch_rows = [assemble_row(s, j) for s, j in zip(batch, judges)]
        if persist and task_id:
            store.save_rows(task_id, batch_rows)
        agg.update(batch_rows)          # 喂累加器后该批即可释放
        done_count += len(batch_rows)
        if on_progress:
            on_progress("judging", done_count, total)


async def run_evaluation(path: str, bu: BUConfig, on_progress=None, task_id=None, persist=False) -> dict:
    """跑一次完整评测。bu 注入该 BU 的领域知识(意图体系/分组/专家身份)。

    persist=True 时逐批落盘,并在重入时跳过已完成行(断点续跑);task_id 为落盘/续跑的键。
    聚合走流式累加器,不在内存保留全量 rows;逐条结果在 t_eval_task_row,前端分页查。
    """
    if on_progress:
        on_progress("loading", 0, 1)
    df, m, filter_stats = load_and_prep(path)
    gold_info = detect_gold(df, m)
    mode = gold_info["mode"]
    samples, excluded_activity = build_all_samples(df, m, bu)
    filter_stats["excluded_activity"] = excluded_activity   # 跳过的活动标问条数,结果页展示
    total = len(samples)
    # 会话级指标基于 samples(judge 前即确定),无需进累加器
    sessions = len(set(s["session"] for s in samples))
    multi_turn = _count_multi_turn(samples)
    if on_progress:
        on_progress("loaded", 1, 1)

    agg = _StreamAggregator()
    await _judge_streaming(samples, bu, on_progress, task_id, persist, agg)

    # 校准指标仅在 calibration 模式算;production 无金标则为空
    metrics = agg.metrics() if mode == "calibration" else []
    intent_dist = agg.intent_distribution()
    insights = agg.insights()
    bu_dispatch = agg.bu_dispatch()
    if on_progress:
        on_progress("advising", 0, 1)
    advice = await generate_advice(insights, bu, bu_dispatch)  # 优化建议(模型或规则)
    if on_progress:
        on_progress("advising", 1, 1)

    summary = {
        "backend": active_backend(),
        "bu": bu.code,
        "bu_name": bu.name,
        "mode": mode,
        "total_samples": total,
        "sessions": sessions,
        "multi_turn_sessions": multi_turn,
        "bu_dispatch": bu_dispatch,                                    # BU 分发漏斗(准确率+两类错误)
        "end_to_end_resolved_rate": insights["overall"]["resolved_rate"],  # 漏斗口径解决率
        "dispatch_accuracy": bu_dispatch["accuracy"],
        "resolved_rate": insights["overall"]["resolved_rate"],
        "needs_review": agg.needs_review,
        "disagreement_count": agg.disagreement_count,
        "errors": agg.errors,
    }

    return {
        "summary": summary,
        "bu": bu.code,
        "bu_name": bu.name,
        "mode": mode,
        "gold_coverage": gold_info["gold_coverage"],
        "filter_stats": filter_stats,
        "metrics": metrics,
        "intent_distribution": intent_dist,
        "insights": insights,
        "advice": advice,
        # rows 不再随结果返回(百万级 OOM);逐条在 t_eval_task_row,前端分页查。
        # disagreements 仅返回有限代表样本,供报表/导出。
        "disagreements": agg.disagreements,
    }


# ── 纯函数:全量 rows 一次算出指标 ────────────────────────────────────────────
# 仅供 tests/eval 做「增量(_StreamAggregator) == 全量」等价校验,不在生产路径调用
# (生产走 _StreamAggregator 流式聚合,百万级不全量驻留)。勿在生产代码引用。


def _compute_metrics(rows: list[dict]) -> list[dict]:
    """对二值金标分别算指标。无金标的维度跳过。"""
    specs = [
        ("分发是否正确", "dispatch", "j_dispatch"),
        ("答案是否解决客户问题", "resolved", "j_resolved"),
    ]
    out = []
    for name, gold_key, j_key in specs:
        y_true, y_pred = [], []
        for r in rows:
            gv = r["gold"].get(gold_key, "")
            jv = r.get(j_key, "")
            if gv in ("是", "否") and jv in ("是", "否"):
                y_true.append(gv)
                y_pred.append(jv)
        if y_true:
            out.append(binary_report(name, y_true, y_pred))
    return out


def _intent_distribution(rows: list[dict]) -> dict:
    """业务分类分布(切片统计)。"""
    intent_counter = Counter(r["j_intent"] for r in rows if r["j_intent"])
    return {
        "by_intent": [{"name": k, "count": v} for k, v in intent_counter.most_common()],
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def compute_insights(rows: list[dict]) -> dict:
    """业务洞察:按业务分类切片算硬指标(生产模式核心产出)。

    每个切片算:样本量、进漏斗数、端到端解决率、需复核占比、未解决典型问题。
    这些是「代码算的硬指标」,后续喂给大模型生成优化建议。
    """
    by_intent: dict[str, list] = defaultdict(list)
    for r in rows:
        intent = r["j_intent"] or "(未分类)"
        by_intent[intent].append(r)

    def slice_stats(name: str, group_rows: list[dict]) -> dict:
        n = len(group_rows)
        # 解决率漏斗口径:分母只算「日志分发到本BU」的样本(拒识/未承接不计入)
        in_bu = [r for r in group_rows if r.get("dispatched_to_bu")]
        resolved_yes = sum(1 for r in in_bu if r["j_resolved_raw"] == "yes")
        need_review = sum(
            1 for r in group_rows
            if isinstance(r["judge"], dict) and r["judge"].get("needs_human_review")
        )
        unresolved_examples = [
            r["question"] for r in in_bu if r["j_resolved_raw"] in ("no", "partial")
        ][:3]
        return {
            "name": name,
            "count": n,
            "in_bu_count": len(in_bu),            # 进入解决度漏斗的数量
            "resolved_rate": _rate(resolved_yes, len(in_bu)),
            "needs_review_rate": _rate(need_review, n),
            "unresolved_examples": unresolved_examples,
        }

    intent_slices = sorted(
        (slice_stats(k, v) for k, v in by_intent.items()),
        key=lambda x: x["count"], reverse=True,
    )

    # 整体端到端解决率:分母 = 分发到本BU的样本(漏斗)
    in_bu_total = [r for r in rows if r.get("dispatched_to_bu")]
    resolved_yes_total = sum(1 for r in in_bu_total if r["j_resolved_raw"] == "yes")
    dispatch_ok_total = sum(1 for r in rows if r.get("dispatch_correct") is True)
    dispatch_scored = sum(1 for r in rows if r.get("dispatch_correct") is not None)
    return {
        "overall": {
            "count": len(rows),
            "in_bu_count": len(in_bu_total),
            "resolved_rate": _rate(resolved_yes_total, len(in_bu_total)),
            "dispatch_accuracy": _rate(dispatch_ok_total, dispatch_scored),
        },
        "by_intent": intent_slices,
    }


def _bu_dispatch_stats(rows: list[dict]) -> dict:
    """BU 分发漏斗:准确率 + 两类错误(漏:该承接却拒识 / 误收:该拒识却承接)。"""
    correct = miss = over = scored = 0
    for r in rows:
        dc = r.get("dispatch_correct")
        if dc is None:
            continue
        scored += 1
        should = bool(r["judge"].get("should_dispatch_to_bu")) if isinstance(r["judge"], dict) else False
        actual = bool(r.get("dispatched_to_bu"))
        if dc:
            correct += 1
        elif should and not actual:
            miss += 1
        elif not should and actual:
            over += 1
    return {
        "scored": scored,
        "correct": correct,
        "wrong": scored - correct,
        "accuracy": round(correct / scored, 4) if scored else 0.0,
        "miss_should_accept_but_rejected": miss,
        "over_should_reject_but_accepted": over,
    }


def _count_multi_turn(samples: list[dict]) -> int:
    sess_turns: dict[str, int] = {}
    for s in samples:
        sess_turns[s["session"]] = max(sess_turns.get(s["session"], 0), s["turn"])
    return sum(1 for v in sess_turns.values() if v > 1)
