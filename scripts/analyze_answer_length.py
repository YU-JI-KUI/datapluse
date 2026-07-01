"""分析评测答案长度分布 + 截断触发情况(只读,不改数据)。

用途:评测的「当前轮答案」在净化器提取不出正文时会兜底截断到 _RAW_MAX_LEN 字。
截断可能切掉关键信息、影响 AI 判解决度。本脚本对真实 Excel 统计:
  - 答案净化后的长度分布(P50/P90/P95/P99/最大)
  - 原文超过截断阈值的条数与占比
  - 实际走到「兜底截断」路径(净化失败)的条数与占比
  - 净化「成功提取」的条数(这些不截断)

据此判断当前 2000 字阈值是否会有害截断,再决定要不要调大/取消。

用法(内网,项目根目录下)：
  uv run python scripts/analyze_answer_length.py <excel路径> [--bu securities|life]
  # 例:
  uv run python scripts/analyze_answer_length.py /data/真实日志.xlsx --bu securities
"""
import argparse
import os
import sys

sys.path.insert(0, "src")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import pandas as pd  # noqa: E402

from datapulse.modules.eval.answer_sanitizer import (  # noqa: E402
    _RAW_MAX_LEN,
    _parse,
    sanitize_answer,
)
from datapulse.modules.eval.pipeline import resolve_columns  # noqa: E402

_TRUNC_MARK = "…(原文超长已截断)"


def _pct(a, b):
    return f"{a}（{(a * 100 / b):.1f}%）" if b else f"{a}（0%）"


def _percentile(sorted_lens, p):
    if not sorted_lens:
        return 0
    return sorted_lens[min(len(sorted_lens) - 1, int(len(sorted_lens) * p))]


def analyze(path: str, bu_code: str) -> None:
    print(f"=== 分析 {path} (bu={bu_code}) ===")
    print(f"当前截断阈值 _RAW_MAX_LEN = {_RAW_MAX_LEN} 字\n")

    df = pd.read_excel(path, dtype=str).fillna("")
    m = resolve_columns(df)          # 缺关键列会直接报错,提示不是标准表
    ans_col = m["answer"]

    n = 0
    truncated = 0            # 净化后带截断标记 = 实际被有害截断
    over_raw = 0            # 原文超阈值(潜在风险)
    extract_ok = 0         # 净化成功提取(命中规则,通常大幅变短、不截断)
    fallback_raw = 0       # 走兜底(非JSON 或 JSON但没命中规则)
    out_lens = []
    longest_examples = []  # 记几条最长的,便于人工看是什么形态

    for raw in df[ans_col]:
        if not raw:
            continue
        n += 1
        out = sanitize_answer(raw, bu_code)
        out_lens.append(len(out))
        if len(raw) > _RAW_MAX_LEN:
            over_raw += 1
        if out.endswith(_TRUNC_MARK):
            truncated += 1
        # 粗判净化是否成功提取:输出明显短于原文且不带截断标记 → 命中规则提取
        if not out.endswith(_TRUNC_MARK) and len(out) < len(raw) * 0.9:
            extract_ok += 1
        else:
            fallback_raw += 1
        longest_examples.append((len(out), out[:120]))

    if n == 0:
        print("没有非空答案。")
        return

    out_lens.sort()
    print(f"答案总数: {n}")
    print(f"净化后长度  P50={_percentile(out_lens, 0.5)}  P90={_percentile(out_lens, 0.9)}  "
          f"P95={_percentile(out_lens, 0.95)}  P99={_percentile(out_lens, 0.99)}  最大={out_lens[-1]}")
    print(f"原文 > {_RAW_MAX_LEN} 字:      {_pct(over_raw, n)}")
    print(f"净化后被有害截断:      {_pct(truncated, n)}   ← 重点!>0 说明有答案被切掉尾部")
    print(f"净化成功提取(不截断):  {_pct(extract_ok, n)}")
    print(f"走兜底原文路径:        {_pct(fallback_raw, n)}   ← 这些没命中净化规则,长则会被截")

    if truncated:
        print("\n【被截断的样例(前 3 条,净化后前 120 字)】")
        shown = [x for x in df[ans_col] if x and sanitize_answer(x, bu_code).endswith(_TRUNC_MARK)][:3]
        for i, raw in enumerate(shown, 1):
            print(f"  {i}. 原文长度 {len(raw)} → {sanitize_answer(raw, bu_code)[:120]}…")

    print("\n【结论参考】")
    if truncated == 0:
        print("  ✅ 当前无答案被有害截断,阈值够用,无需调整。")
    else:
        print(f"  ⚠️ 有 {truncated} 条被截断,可能切掉关键信息。建议:")
        print(f"     - 若这些是长文本正确答案 → 调大 _RAW_MAX_LEN(answer_sanitizer.py)")
        print(f"     - 若是净化器没认识的结构 → 给 answer_sanitizer 补一条提取规则")


def main():
    ap = argparse.ArgumentParser(description="分析评测答案长度分布与截断触发情况")
    ap.add_argument("excel", help="日志 Excel 路径(需含「答案」列)")
    ap.add_argument("--bu", default="securities", help="业务单元:securities / life(影响证券专属净化)")
    args = ap.parse_args()
    if not os.path.exists(args.excel):
        print(f"文件不存在: {args.excel}")
        sys.exit(1)
    analyze(args.excel, args.bu)


if __name__ == "__main__":
    main()
