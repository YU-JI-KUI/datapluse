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


def binary_report(name: str, y_true: list[str], y_pred: list[str]) -> dict:
    """对一个二值维度算全套指标,返回结构化 dict(供 API/前端用)。"""
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=_LABELS, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=_LABELS).tolist()
    per_label = {
        lab: {"precision": float(pp), "recall": float(rr), "f1": float(ff)}
        for lab, pp, rr, ff in zip(_LABELS, p, r, f)
    }
    # 宏平均 F1:两个类别 F1 的简单平均,类别不均衡时比 accuracy 更能反映真实表现
    macro_f1 = float(sum(f) / len(f)) if len(f) else 0.0
    return {
        "name": name,
        "n": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "kappa": float(cohen_kappa_score(y_true, y_pred)) if len(set(y_true)) > 1 else 0.0,
        "macro_f1": macro_f1,
        "labels": _LABELS,
        "per_label": per_label,
        # 混淆矩阵 [真值是/否] x [预测是/否]
        "confusion_matrix": cm,
    }
