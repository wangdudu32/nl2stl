"""Strict Semantic Robustness metric for STL formulas."""

from __future__ import annotations

from semantic_robustness import DATASET_PATH, SEED, semantic_scores_for_pair
from stl_metrics_utils import load_records, mean
from stl_syntax_validator import validate_record


def strict_semantic_robustness(file_path: str) -> float:
    """返回全部采样轨迹上满足性均一致的样本比例。"""
    scores: list[float] = []
    for index, record in enumerate(load_records(file_path)):
        pred_formula = record["pred_stl"]
        if validate_record(record) is not None:
            scores.append(0.0)
            continue
        try:
            scores.append(strict_semantic_robustness_for_pair(record["gold_stl"], pred_formula, SEED + index))
        except Exception as error:
            raise RuntimeError(
                f"Strict semantic robustness failed at taskid={record['taskid']}\n"
                f"gold_stl={record['gold_stl']}\n"
                f"pred_stl={pred_formula}\n{error}"
            ) from error
    return mean(scores)


def strict_semantic_robustness_for_pair(gold_formula: str, pred_formula: str, seed: int) -> float:
    """与普通语义指标使用同一批轨迹和一致的随机种子。"""
    _, score = semantic_scores_for_pair(gold_formula, pred_formula, seed)
    return score


if __name__ == "__main__":
    import sys

    print(strict_semantic_robustness(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
