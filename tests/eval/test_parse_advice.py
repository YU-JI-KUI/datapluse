"""parse_advice 容错测试:大模型返回的脏 JSON 不该让整段建议丢失。

复现内网报错 `Expecting ',' delimiter`:模型吐的不是干净纯 JSON 时,
能救多少救多少,而不是一炸全降级到规则。
"""
from datapulse.modules.eval.advisor import parse_advice

FENCE = chr(96) * 3


def test_clean_array():
    text = '[{"scope":"交易","severity":"high","problem":"a"}]'
    out = parse_advice(text)
    assert len(out) == 1 and out[0]["scope"] == "交易"


def test_markdown_fence():
    text = f'{FENCE}json\n[{{"scope":"x","severity":"low"}}]\n{FENCE}'
    assert len(parse_advice(text)) == 1


def test_preamble_and_trailing_text():
    # 模型掺前言后语,剥围栏剥不掉,靠截取 [..] 边界救回
    text = '以下是我的优化建议:\n[{"scope":"x","severity":"high"}]\n希望对你有帮助。'
    out = parse_advice(text)
    assert len(out) == 1 and out[0]["scope"] == "x"


def test_trailing_comma():
    # 末尾多一个逗号,标准 json.loads 会炸,整体失败后逐个救
    text = '[{"scope":"a","severity":"high"},{"scope":"b","severity":"low"},]'
    out = parse_advice(text)
    assert len(out) == 2


def test_one_broken_object_others_survive():
    # 第二条 evidence 里有未转义引号导致该对象语法坏,其余两条仍要保住
    text = (
        '[{"scope":"a","severity":"high","problem":"ok"},'
        '{"scope":"b","severity":"mid","evidence":"漏收 "5" 条"},'
        '{"scope":"c","severity":"low","problem":"ok2"}]'
    )
    out = parse_advice(text)
    scopes = {x["scope"] for x in out}
    assert "a" in scopes and "c" in scopes  # 好的两条救回
    assert len(out) >= 2


def test_brace_inside_string_not_treated_as_object():
    # suggestion 文本里带花括号,不能被当成对象边界切断
    text = '[{"scope":"x","severity":"high","suggestion":"补标问 {symbol} 占位"}]'
    out = parse_advice(text)
    assert len(out) == 1 and "{symbol}" in out[0]["suggestion"]


def test_empty_and_garbage():
    assert parse_advice("") == []
    assert parse_advice("模型这次没给出有效建议") == []


def test_non_dict_items_filtered():
    text = '[{"scope":"x","severity":"high"}, "noise", 42]'
    out = parse_advice(text)
    assert len(out) == 1 and out[0]["scope"] == "x"
