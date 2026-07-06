"""按业务分类提炼高区分关键词（jieba 分词 + TF-IDF）。

以「每个业务分类的问题合集」为一篇文档，跨分类做 TF-IDF：某词在本分类频繁、
在别的分类罕见 → 权重高，即该分类的区分性关键词。纯展示，不回填规则表。

jieba / sklearn 首次导入慢（词典 + OpenMP），故延迟到函数内 import，
不在模块顶层触发（见 CLAUDE.md ML 库 OpenMP 规范）。
"""

from __future__ import annotations

import re

# 常见中文停用词 + 客服问句里的高频虚词（这些词区分度低，剔除避免污染关键词）
_STOP = {
    "的", "了", "吗", "呢", "啊", "吧", "是", "我", "你", "他", "她", "它",
    "怎么", "如何", "什么", "为什么", "哪里", "哪个", "多少", "可以", "能否",
    "需要", "想", "要", "请问", "咨询", "一下", "这个", "那个", "有没有",
    "和", "与", "或", "在", "对", "把", "被", "给", "让", "会", "不", "没",
    "个", "一", "这", "那", "就", "都", "也", "还", "又", "呀", "嘛",
}

_NON_WORD = re.compile(r"^[\d\W_]+$")


def _tokenize(text: str) -> list[str]:
    import jieba

    words = []
    for w in jieba.cut(str(text or "")):
        w = w.strip()
        if len(w) < 2:              # 剔单字（区分度低）
            continue
        if w in _STOP:
            continue
        if _NON_WORD.match(w):      # 纯数字/标点
            continue
        words.append(w)
    return words


def extract_by_intent(
    rows: list[tuple[str, str]], top_n: int = 15, min_intent_docs: int = 3
) -> list[dict]:
    """rows = [(question, intent), ...]。按 intent 分组做 TF-IDF，每组取 top_n 关键词。

    返回 [{"intent": str, "keywords": [{"word": str, "weight": float}, ...]}, ...]，
    按该分类问题数降序。问题数少于 min_intent_docs 的分类跳过（样本太少无意义）。
    """
    from collections import defaultdict

    groups: dict[str, list[str]] = defaultdict(list)
    for q, intent in rows:
        key = (intent or "未分类").strip() or "未分类"
        groups[key].append(q)

    intents = [k for k, v in groups.items() if len(v) >= min_intent_docs]
    if not intents:
        return []

    # 每个分类拼成一篇文档（空格分隔分好的词），跨分类做 TF-IDF
    docs = [" ".join(tok for q in groups[i] for tok in _tokenize(q)) for i in intents]

    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(token_pattern=r"(?u)\S+")  # 已分好词，按空白切
    matrix = vec.fit_transform(docs)
    vocab = vec.get_feature_names_out()

    out = []
    for row_i, intent in enumerate(intents):
        weights = matrix[row_i].toarray()[0]
        ranked = sorted(
            ((vocab[j], float(weights[j])) for j in range(len(vocab)) if weights[j] > 0),
            key=lambda x: x[1], reverse=True,
        )[:top_n]
        out.append({
            "intent": intent,
            "doc_count": len(groups[intent]),
            "keywords": [{"word": w, "weight": round(wt, 4)} for w, wt in ranked],
        })
    out.sort(key=lambda g: g["doc_count"], reverse=True)
    return out
