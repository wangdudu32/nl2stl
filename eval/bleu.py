"""BLEU metric for STL formulas."""

from __future__ import annotations

from stl_syntax_validator import stl_syntax_validator
from stl_metrics_utils import bleu_score, load_records, mean, tokenize_formula

DATASET_PATH = "data.txt"


def BLEU(file_path: str) -> float:
    """Return macro-average smoothed BLEU-4 over STL token sequences."""
    scores: list[float] = []
    for record in load_records(file_path):
        pred_formula = record["pred_stl"]
        if not stl_syntax_validator(pred_formula):
            scores.append(0.0)
            continue
        scores.append(
            bleu_score(
                tokenize_formula(record["gold_stl"]),
                tokenize_formula(pred_formula),
            )
        )
    return mean(scores)


if __name__ == "__main__":
    import sys

    print(BLEU(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
