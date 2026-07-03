"""答案解析覆盖率分析：扫日志 Excel 的「答案」列，看当前解析器覆盖了哪些、漏了哪些。

用于找「漏网之鱼」——是 JSON 但没有任何解析器认领的答案结构，这些需要新写解析器。

输出：
  1. 各解析器命中条数（覆盖情况）
  2. 非 JSON（纯文本）条数
  3. 漏网之鱼（是 JSON 但没解析器认领）——按「结构签名」聚类，
     每种结构给出条数 + 一个样例，方便判断要新增几个解析器、怎么写

用法（内网，项目根目录）：
  uv run python scripts/answer_coverage.py <excel路径> [--bu securities|life] [--top 15] [--sample-len 400]

  <excel路径>    日志 Excel（需含「答案」列）
  --bu           业务单元（影响专属解析器；默认 securities）
  --top          漏网结构最多展示几类（默认 15）
  --sample-len   每个样例打印多少字符（默认 400）
"""
import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, "src")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import pandas as pd  # noqa: E402

from datapulse.modules.eval.answer_sanitizer import diagnose  # noqa: E402
from datapulse.modules.eval.answer_sanitizer.base import parse_json  # noqa: E402
from datapulse.modules.eval.pipeline import resolve_columns  # noqa: E402


def _signature(raw: str) -> str:
    """给一条答案算「结构签名」，用于把同结构的漏网答案聚到一起。

    - JSON 对象：顶层 key 排序拼接（如 msgContext|type）
    - JSON 数组：list[首元素签名]
    - 其它：按类型标记
    """
    p = parse_json(raw)
    return _sig_of(p)


def _sig_of(obj, depth=0) -> str:
    if depth > 2:
        return "…"
    if isinstance(obj, dict):
        return "{" + ",".join(sorted(obj.keys())) + "}"
    if isinstance(obj, list):
        return "[" + (_sig_of(obj[0], depth + 1) if obj else "") + "]"
    if obj is None:
        return "非JSON"
    return type(obj).__name__


def analyze(path: str, bu: str, top: int, sample_len: int) -> None:
    print(f"=== 答案解析覆盖率分析 {path} (bu={bu}) ===\n")
    df = pd.read_excel(path, dtype=str).fillna("")
    m = resolve_columns(df)          # 缺关键列会直接报错，提示不是标准表
    answers = [a for a in df[m["answer"]] if a and a.strip()]
    n = len(answers)
    if n == 0:
        print("没有非空答案。")
        return

    hit_by_parser = Counter()        # 各解析器命中数
    non_json = 0                     # 非 JSON（纯文本）
    unmatched_sig = Counter()        # 漏网结构签名 → 条数
    unmatched_sample = {}            # 漏网结构签名 → 一个样例

    for raw in answers:
        d = diagnose(raw, bu)
        if d["matched"]:
            hit_by_parser[d["parser"]] += 1
        elif not d["is_json"]:
            non_json += 1
        else:
            sig = _signature(raw)
            unmatched_sig[sig] += 1
            unmatched_sample.setdefault(sig, raw)

    matched = sum(hit_by_parser.values())
    unmatched_json = sum(unmatched_sig.values())

    print(f"答案总数：{n}")
    print(f"  ✅ 解析器命中：{matched}（{matched*100//n}%）")
    print(f"  📄 纯文本(非JSON)：{non_json}（{non_json*100//n}%）  ← 无需解析，原样即可")
    print(f"  ⚠️ 漏网之鱼(是JSON但没解析器认领)：{unmatched_json}（{unmatched_json*100//n}%）\n")

    print("── 各解析器命中分布 ──")
    for name, c in hit_by_parser.most_common():
        print(f"  {name:28} {c}")
    if not hit_by_parser:
        print("  （无命中）")

    print(f"\n── 漏网结构聚类（Top {top}，需为这些新写解析器）──")
    if not unmatched_sig:
        print("  🎉 没有漏网的 JSON 答案，当前解析器已覆盖全部 JSON 结构。")
    for sig, c in unmatched_sig.most_common(top):
        print(f"\n  [{c} 条] 结构签名: {sig}")
        sample = unmatched_sample[sig]
        print(f"    样例: {sample[:sample_len]}" + ("…" if len(sample) > sample_len else ""))
    remain = len(unmatched_sig) - top
    if remain > 0:
        print(f"\n  …另有 {remain} 种漏网结构未展示（--top 调大可看全）")


def main():
    ap = argparse.ArgumentParser(description="答案解析覆盖率分析：找没被解析器覆盖的答案结构")
    ap.add_argument("excel", help="日志 Excel 路径（需含「答案」列）")
    ap.add_argument("--bu", default="securities", help="业务单元：securities / life")
    ap.add_argument("--top", type=int, default=15, help="漏网结构最多展示几类")
    ap.add_argument("--sample-len", type=int, default=400, help="每个样例打印多少字符")
    args = ap.parse_args()
    if not os.path.exists(args.excel):
        print(f"文件不存在: {args.excel}")
        sys.exit(1)
    analyze(args.excel, args.bu, args.top, args.sample_len)


if __name__ == "__main__":
    main()
