"""Strict Semantic Robustness metric for STL formulas."""

from __future__ import annotations

import random

from semantic_robustness import (
    DATASET_PATH,
    MAX_HORIZON,
    SEED,
    TRACE_COUNT,
    build_spec,
    discretize_intervals,
    extract_numeric_thresholds,
    generate_trace,
    max_interval_end,
    satisfies,
)
from stl_metrics_utils import load_records, mean, tokenize_formula
from stl_syntax_validator import extract_variables, stl_syntax_validator


def strict_semantic_robustness(file_path: str) -> float:
    """Return macro-average all-trace satisfaction agreement."""
    scores: list[float] = []
    for index, record in enumerate(load_records(file_path)):
        pred_formula = record["pred_stl"]
        if not stl_syntax_validator(pred_formula):
            scores.append(0.0)
            continue
        try:
            scores.append(strict_semantic_robustness_for_pair(record["gold_stl"], pred_formula, SEED + index))
        except Exception as exc:
            taskid = record.get("taskid", index)
            raise RuntimeError(
                f"Strict semantic robustness failed at taskid={taskid}\n"
                f"gold_stl={record['gold_stl']}\n"
                f"pred_stl={pred_formula}"
            ) from exc
    return mean(scores)


def strict_semantic_robustness_for_pair(gold_formula: str, pred_formula: str, seed: int) -> float:
    if tokenize_formula(gold_formula) == tokenize_formula(pred_formula):
        return 1.0

    variables = sorted(extract_variables(gold_formula) | extract_variables(pred_formula))
    if not variables:
        return 0.0

    gold_formula = discretize_intervals(gold_formula)
    pred_formula = discretize_intervals(pred_formula)
    gold_spec = build_spec(gold_formula, variables)
    pred_spec = build_spec(pred_formula, variables)
    horizon = min(max(max_interval_end(gold_formula), max_interval_end(pred_formula), 10), MAX_HORIZON)
    thresholds = extract_numeric_thresholds(gold_formula + " " + pred_formula)
    rng = random.Random(seed)
    for _ in range(TRACE_COUNT):
        trace = generate_trace(variables, thresholds, horizon, rng)
        if satisfies(gold_spec, trace) != satisfies(pred_spec, trace):
            return 0.0
    return 1.0


if __name__ == "__main__":
    import sys

    print(strict_semantic_robustness(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
