"""Template Accuracy metric."""

from __future__ import annotations

from stl_syntax_validator import validate_record
from stl_metrics_utils import (
    load_records,
    mean,
    positional_accuracy,
    template_tokens,
)

DATASET_PATH = "data.txt"


def Template_Accuracy(file_path: str) -> float:
    """返回各样本抽象模板位置匹配率的平均值。"""
    scores: list[float] = []
    for record in load_records(file_path):
        pred_formula = record["pred_stl"]
        if validate_record(record) is not None:
            scores.append(0.0)
            continue
        scores.append(template_accuracy_for_pair(record["gold_stl"], pred_formula))
    return mean(scores)


def template_accuracy_for_pair(gold_formula: str, pred_formula: str) -> float:
    """计算一对已通过语法校验的公式。"""
    return positional_accuracy(template_tokens(gold_formula), template_tokens(pred_formula))


if __name__ == "__main__":
    import sys

    print(Template_Accuracy(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
