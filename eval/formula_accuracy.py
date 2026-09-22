"""Formula Accuracy metric."""

from __future__ import annotations

from stl_syntax_validator import validate_record
from stl_metrics_utils import (
    load_records,
    mean,
    positional_accuracy,
    tokenize_formula,
)

DATASET_PATH = "data.txt"


def Formula_Accuracy(file_path: str) -> float:
    """返回各样本 token 位置匹配率的平均值。"""
    scores: list[float] = []
    for record in load_records(file_path):
        pred_formula = record["pred_stl"]
        if validate_record(record) is not None:
            scores.append(0.0)
            continue
        scores.append(formula_accuracy_for_pair(record["gold_stl"], pred_formula))
    return mean(scores)


def formula_accuracy_for_pair(gold_formula: str, pred_formula: str) -> float:
    """计算一对已通过语法校验的公式。"""
    return positional_accuracy(tokenize_formula(gold_formula), tokenize_formula(pred_formula))


if __name__ == "__main__":
    import sys

    print(Formula_Accuracy(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
