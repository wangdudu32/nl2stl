"""Template Accuracy metric."""

from __future__ import annotations

from stl_syntax_validator import stl_syntax_validator
from stl_metrics_utils import (
    load_records,
    mean,
    positional_accuracy,
    template_tokens,
)

DATASET_PATH = "data.txt"


def Template_Accuracy(file_path: str) -> float:
    """Return macro-average positional accuracy after STL template abstraction."""
    scores: list[float] = []
    for record in load_records(file_path):
        pred_formula = record["pred_stl"]
        if not stl_syntax_validator(pred_formula):
            scores.append(0.0)
            continue
        scores.append(
            positional_accuracy(
                template_tokens(record["gold_stl"]),
                template_tokens(pred_formula),
            )
        )
    return mean(scores)


if __name__ == "__main__":
    import sys

    print(Template_Accuracy(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
