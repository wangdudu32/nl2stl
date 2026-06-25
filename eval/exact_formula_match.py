"""Exact Formula Match metric."""

from __future__ import annotations

from stl_syntax_validator import stl_syntax_validator
from stl_metrics_utils import load_records, mean, tokenize_formula

DATASET_PATH = "data.txt"


def Exact_Formula_Match(file_path: str) -> float:
    """Return the ratio of samples whose predicted STL exactly matches gold STL."""
    scores: list[float] = []
    for record in load_records(file_path):
        pred_formula = record["pred_stl"]
        if not stl_syntax_validator(pred_formula):
            scores.append(0.0)
            continue
        gold_tokens = tokenize_formula(record["gold_stl"])
        pred_tokens = tokenize_formula(pred_formula)
        scores.append(1.0 if pred_tokens == gold_tokens else 0.0)
    return mean(scores)


if __name__ == "__main__":
    import sys

    print(Exact_Formula_Match(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
