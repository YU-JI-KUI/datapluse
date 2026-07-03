"""从标注的「关键词说明」按业务分类逐类提炼通用业务规则（调 LLM）。

背景：标注员写的 keywords_desc 是「个案说明」（这条为什么这么标），量大、碎片、
有噪声，不能直接当业务规则灌进 Judge 提示词。本脚本按业务分类**逐个**提炼——
每个分类单独一次 LLM 调用（避免所有分类挤一个上下文导致溢出/迷失），把该类下几十
上百条个案说明归纳成 2~3 条可泛化的通用规则。

产出仅供**人工审阅**，审阅后再挑进寿险 business_knowledge.md，别直接全量套用。

用法（内网，项目根目录）：
  uv run python scripts/extract_rules.py <dataset_id> [--out rules_draft.md] [--min-count 1] [--top 40]

  <dataset_id>   目标数据集 ID
  --out          提炼结果写入的 md 文件（默认打印到终端）
  --min-count    只喂出现次数≥此值的说明（过滤长尾噪声，默认 1=全要）
  --top          每个分类最多喂多少条说明给 LLM（防单类过多，默认 40）

前置：需能连库 + judge_backend=pingan 且 LLM 变量齐全（复用评测的 call_bigmodel_api）。
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from sqlalchemy import text  # noqa: E402

from datapulse.config.settings import get_settings  # noqa: E402
from datapulse.modules.eval.llm.pingan_client import (  # noqa: E402
    call_bigmodel_api,
    extract_content,
)
from datapulse.repository import get_db, init_db  # noqa: E402

_SYSTEM = (
    "你是寿险业务的评测规则专家。下面给你「某个业务分类」下，人工标注员写的一批关键词说明"
    "（每条是对某条数据为何这么标的个案解释）。请你归纳成 **2~3 条可泛化的通用判定规则**，"
    "用于指导 AI 评测这类问题。要求：\n"
    "1. 只输出规则，每条一行，以「- 」开头；不要复述原文、不要解释、不要编号。\n"
    "2. 规则要通用（换一条相似问题仍成立），不要写成只对某一条成立的个案。\n"
    "3. 语言精炼、可直接作为判定依据；剔除自相矛盾/明显错误的个案说明。\n"
    "4. 若这批说明质量太差、归纳不出可靠规则，只输出一行：- （无可靠通用规则）"
)


def _fetch_categories(dataset_id: int) -> list[str]:
    with get_db().engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT a.category FROM t_annotation a "
            "JOIN t_data_item di ON di.id = a.data_id "
            "WHERE di.dataset_id = :did AND a.is_active = TRUE "
            "AND TRIM(COALESCE(a.category,'')) <> '' ORDER BY a.category"
        ), {"did": dataset_id}).all()
    return [r[0] for r in rows]


def _fetch_descs(dataset_id: int, category: str, min_count: int, top: int) -> list[tuple[str, int]]:
    """取某分类下去重+频次的关键词说明，按频次降序，最多 top 条。"""
    with get_db().engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT TRIM(a.keywords_desc) AS d, COUNT(*) AS c "
            "FROM t_annotation a JOIN t_data_item di ON di.id = a.data_id "
            "WHERE di.dataset_id = :did AND a.is_active = TRUE AND a.category = :cat "
            "AND TRIM(COALESCE(a.keywords_desc,'')) <> '' "
            "GROUP BY TRIM(a.keywords_desc) HAVING COUNT(*) >= :mc "
            "ORDER BY c DESC LIMIT :top"
        ), {"did": dataset_id, "cat": category, "mc": min_count, "top": top}).all()
    return [(r[0], r[1]) for r in rows]


async def _distill(category: str, descs: list[tuple[str, int]]) -> str:
    s = get_settings()
    lines = "\n".join(f"（{c}次）{d}" for d, c in descs)
    user = f"业务分类：{category}\n\n关键词说明（个案，括号是出现次数）：\n{lines}"
    resp = await call_bigmodel_api(
        query=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        scene_id=s.llm_scene_id, app_key=s.llm_app_key, app_secret=s.llm_app_secret,
        timeout=s.llm_timeout, max_retries=s.llm_max_retries,
    )
    if isinstance(resp, dict) and resp.get("error"):
        return f"- （提炼失败：{resp['error']}）"
    return extract_content(resp).strip()


async def run(dataset_id: int, out_path: str | None, min_count: int, top: int) -> None:
    cats = _fetch_categories(dataset_id)
    if not cats:
        print(f"dataset {dataset_id} 下没有带业务分类的有效标注。")
        return
    print(f"共 {len(cats)} 个业务分类，逐个提炼中…\n")

    blocks = [f"# 寿险业务规则草稿（dataset {dataset_id} · 从标注关键词说明提炼）\n",
              "> 每类由 LLM 从个案说明归纳，**仅供人工审阅**，挑选后再放进 business_knowledge。\n"]
    for i, cat in enumerate(cats, 1):
        descs = _fetch_descs(dataset_id, cat, min_count, top)
        if not descs:
            print(f"[{i}/{len(cats)}] {cat}：无符合条件的说明，跳过")
            continue
        print(f"[{i}/{len(cats)}] {cat}：喂 {len(descs)} 条说明，提炼中…")
        rules = await _distill(cat, descs)
        block = f"## {cat}\n\n{rules}\n"
        blocks.append(block)
        print(block)

    doc = "\n".join(blocks)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(doc)
        print(f"\n✅ 已写入 {out_path}（请人工审阅后挑进 business_knowledge）")


def main():
    ap = argparse.ArgumentParser(description="按业务分类从关键词说明逐类提炼通用规则")
    ap.add_argument("dataset_id", type=int, help="目标数据集 ID")
    ap.add_argument("--out", default=None, help="结果写入的 md 文件（默认仅打印）")
    ap.add_argument("--min-count", type=int, default=1, help="只喂出现次数≥此值的说明")
    ap.add_argument("--top", type=int, default=40, help="每类最多喂多少条说明给 LLM")
    args = ap.parse_args()

    s = get_settings()
    init_db(s.db_url, connect_args=s.db_connect_args, db_url_safe=s.db_url_safe)
    if s.judge_backend != "pingan" or not s.pingan_ready():
        print("⚠️ 当前非 pingan 后端或 LLM 变量不全，无法调真实模型提炼。请配置后再跑。")
        sys.exit(1)
    asyncio.run(run(args.dataset_id, args.out, args.min_count, args.top))


if __name__ == "__main__":
    main()
