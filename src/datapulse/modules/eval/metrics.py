"""校准指标计算:对二值人工金标算 准/召/F1 + 混淆矩阵 + Cohen's κ。

可信校准目标 = 两个二值金标:
  - 分发是否正确(AV) / 一键场景分发是否正确(AW)
  - 答案是否解决客户问题(AY)
意图细分类暂只作信息(无干净真值),不在此严格校准。

Cohen's κ(Kappa):衡量「Judge 与人工」两个标注者一致性的统计量,
扣除了「碰巧一致」的部分。κ=1 完全一致,κ=0 等于瞎猜,越高越可信。
对 Java 背景:可以理解成比「准确率」更严格的一致性分数。
"""
from __future__ import annotations

from sklearn.metrics import (
    accuracy_score,
    cohen_kappa_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

_LABELS = ["是", "否"]


def binary_report(name: str, y_true: list[str], y_pred: list[str],
                  sample_weight: list[int] | None = None) -> dict:
    """对一个二值维度算全套指标,返回结构化 dict(供 API/前端用)。

    sample_weight:每条配对的权重(计数)。流式累加器只保留 4 种「是/否」配对的
    计数,finalize 时传入 4 元代表序列 + 权重,结果与全量展开完全等价(避免百万级
    金标全量驻留内存)。默认 None 时行为不变,保持纯函数契约。
    """
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=_LABELS, zero_division=0, sample_weight=sample_weight
    )
    cm = confusion_matrix(y_true, y_pred, labels=_LABELS, sample_weight=sample_weight)
    cm = cm.astype(int).tolist()   # 带权重时 cm 为 float,转回整数计数
    per_label = {
        lab: {"precision": float(pp), "recall": float(rr), "f1": float(ff)}
        for lab, pp, rr, ff in zip(_LABELS, p, r, f)
    }
    # 宏平均 F1:两个类别 F1 的简单平均,类别不均衡时比 accuracy 更能反映真实表现
    macro_f1 = float(sum(f) / len(f)) if len(f) else 0.0
    n = int(sum(sample_weight)) if sample_weight is not None else len(y_true)
    distinct_true = (
        {t for t, w in zip(y_true, sample_weight) if w > 0}
        if sample_weight is not None else set(y_true)
    )
    return {
        "name": name,
        "n": n,
        "accuracy": float(accuracy_score(y_true, y_pred, sample_weight=sample_weight)),
        "kappa": (
            float(cohen_kappa_score(y_true, y_pred, sample_weight=sample_weight))
            if len(distinct_true) > 1 else 0.0
        ),
        "macro_f1": macro_f1,
        "labels": _LABELS,
        "per_label": per_label,
        # 混淆矩阵 [真值是/否] x [预测是/否]
        "confusion_matrix": cm,
    }
