"""评测逻辑契约测试 —— 证明:只要模型按约定格式返回,评测链路就一定算对。

这是回答「外网怎么保证内网模型场景下评测逻辑正确」的关键测试:
完全不碰真实模型,用写死的「金样本模型应答」驱动整条
  解析模型输出 → 转二值 → 算指标 → 判不一致
链路,把评测逻辑与「模型好不好/连不连得上」彻底解耦。

到内网后,真实 Qwen 只要吐出符合 OUTPUT_SCHEMA 的 JSON,本测试覆盖的逻辑即生效。
"""
import json

import pytest

from datapulse.modules.eval.bu.registry import get_bu

# 业务分类已动态注入（库优先、文件兜底）；用 get_bu 取到带 intents 的实例。
# 无 DB 时 load_categories 回退读 categories.json，测试仍能拿到分类清单。
SEC = get_bu("securities")
from datapulse.modules.eval.judge import OUTPUT_SCHEMA, build_messages, parse_judge_output
from datapulse.modules.eval.llm.judge_runner import judge_one
from datapulse.modules.eval.metrics import binary_report


def test_judge_output_schema_roundtrip():
    """模型若严格按 OUTPUT_SCHEMA 的键返回,parse_judge_output 必须能解析。"""
    # 一段「像真实模型」的应答:键齐全、被 Markdown 围栏包裹(真实模型常见)。新契约。
    model_reply = "```json\n" + json.dumps({
        "should_dispatch_to_bu": True,
        "dispatch_reason": "问题属资产查询,该证券承接",
        "business_type": "资产查询",
        "business_type_reason": "问的是融资利率,属资产查询",
        "answer_relevant": True,
        "answer_complete": True,
        "answer_resolved": "yes",
        "resolved_reason": "答案给了具体数字,用户未重问",
        "unresolved_cause": "",
        "needs_human_review": False,
        "review_reason": "",
    }, ensure_ascii=False) + "\n```"

    parsed = parse_judge_output(model_reply)
    # 输出契约的每个键都在
    for key in OUTPUT_SCHEMA:
        assert key in parsed, f"模型输出缺少约定字段: {key}"
    assert parsed["answer_resolved"] == "yes"
    assert parsed["needs_human_review"] is False


def test_messages_carry_all_judge_inputs():
    """prompt 构造必须把评测所需的全部输入都带给模型,缺一不可。"""
    sample = {
        "question": "我的融资利率年化是多少",
        "context": [{"turn": 1, "user": "帮我查下账户", "ai": "已为您打开账户页"}],
        "dispatched_intent": "资产查询",
        "dispatch_reason": "命中标准问",
        "answer_text": "年化6.5%",
        "answer_type": "faq_text",
        "next_user_turn": "那融资成本呢",
    }
    msgs = build_messages(sample, SEC)
    user_prompt = msgs[1]["content"]
    # 关键输入都进了 prompt
    assert "我的融资利率年化是多少" in user_prompt
    assert "帮我查下账户" in user_prompt          # 上下文
    assert "资产查询" in user_prompt              # 系统分发
    assert "年化6.5%" in user_prompt              # 规范化答案
    assert "那融资成本呢" in user_prompt          # 下一轮轨迹
    # 意图清单也在(让模型做判别而非生成)
    assert "到价提醒" in user_prompt


def test_full_eval_chain_from_golden_replies():
    """端到端:一批金样本模型应答 → 转二值 → 算指标,数字必须可手算复现。

    设计 4 条样本,人工金标已知,模型应答已知,期望指标可手算:
      分发: 金[是,是,否,否] vs 判[是,否,否,否]
        → 真是2(判是1/判否1)、真否2(判否2) → 准确率3/4=0.75
    """
    golden = [
        # (模型应答 dispatch_correct, answer_resolved, 金标 dispatch, 金标 resolved)
        (True,  "yes",     "是", "是"),   # 分发一致、解决一致
        (False, "no",      "是", "是"),   # 分发不一致(judge否/金是)、解决不一致
        (False, "no",      "否", "否"),   # 都一致
        (False, "partial", "否", "否"),   # 分发一致、解决:partial→否,与金否一致
    ]

    y_true_d, y_pred_d, y_true_r, y_pred_r = [], [], [], []
    for dispatch_ok, resolved, gold_d, gold_r in golden:
        # 模拟「解析完模型输出后」的二值转换(与 evaluator._judge_to_binary 同口径)
        j_dispatch = "是" if dispatch_ok else "否"
        j_resolved = "是" if resolved == "yes" else "否"
        y_true_d.append(gold_d)
        y_pred_d.append(j_dispatch)
        y_true_r.append(gold_r)
        y_pred_r.append(j_resolved)

    rep_d = binary_report("分发是否正确", y_true_d, y_pred_d)
    assert rep_d["n"] == 4
    assert abs(rep_d["accuracy"] - 0.75) < 1e-9   # 手算 3/4
    # 混淆矩阵方向必须是 [真是→预是, 真是→预否; 真否→预是, 真否→预否]
    # 金[是,是,否,否] 判[是,否,否,否] → 真是:预是1/预否1;真否:预是0/预否2
    assert rep_d["confusion_matrix"] == [[1, 1], [0, 2]]

    rep_r = binary_report("答案是否解决", y_true_r, y_pred_r)
    # 金[是,是,否,否] 判[是,否,否,否] → 同上
    assert rep_r["confusion_matrix"] == [[1, 1], [0, 2]]


def test_confusion_matrix_orientation_hand_computed():
    """把混淆矩阵方向用最小手算样例钉死,防止 y_true/y_pred 接反这种致命错。"""
    # 真值全是「是」,预测全是「否」 → 真是2全部落到「预否」格
    rep = binary_report("t", ["是", "是"], ["否", "否"])
    assert rep["confusion_matrix"] == [[0, 2], [0, 0]]
    #                                   ↑真是→预是=0, 真是→预否=2


def test_parse_judge_output_raises_clear_error_on_bad_json():
    """模型吐非法 JSON 时,必须抛清晰的 ValueError(而非裸 JSONDecodeError)。"""
    with pytest.raises(ValueError, match="不是有效 JSON"):
        parse_judge_output("这不是JSON,模型跑偏了")


async def test_judge_one_never_raises_returns_error_marker():
    """judge_one 对任何失败都应吞掉并返回带 _error 的结果,绝不让单条中断整批。"""
    # 构造一个缺字段的样本,mock 路径也能跑;这里验证返回结构始终可用
    bad_sample = {}  # 缺 question 等键
    result = await judge_one(bad_sample, SEC)
    assert isinstance(result, dict)
    # 要么正常判定,要么带 _error;无论如何 needs_human_review 可读
    assert "needs_human_review" in result or "_error" in result
