"""Semantic Robustness metric for STL formulas."""

from __future__ import annotations

import math
import random
import re

import rtamt

from stl_metrics_utils import load_records, mean, tokenize_formula
from stl_syntax_validator import extract_variables, stl_syntax_validator

DATASET_PATH = "data.txt"
TRACE_COUNT = 10
MAX_HORIZON = 200
SEED = 13

NUMBER_RE = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
COMPARATOR_RE = r"<=|>=|==|!=|(?<![-<>=])<(?![-=>])|(?<![-<>=])>(?!=)|(?<![<>=])=(?![=>])"


def Semantic_Robustness(file_path: str) -> float:
    """Return macro-average satisfaction agreement over sampled traces."""
    scores: list[float] = []
    for index, record in enumerate(load_records(file_path)):
        pred_formula = record["pred_stl"]
        if not stl_syntax_validator(pred_formula):
            scores.append(0.0)
            continue
        try:
            scores.append(semantic_robustness_for_pair(record["gold_stl"], pred_formula, SEED + index))
        except Exception as exc:
            taskid = record.get("taskid", index)
            raise RuntimeError(
                f"Semantic robustness failed at taskid={taskid}\n"
                f"gold_stl={record['gold_stl']}\n"
                f"pred_stl={pred_formula}"
            ) from exc
    return mean(scores)


def semantic_robustness_for_pair(gold_formula: str, pred_formula: str, seed: int) -> float:
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

    matches = 0
    for _ in range(TRACE_COUNT):
        trace = generate_trace(variables, thresholds, horizon, rng)
        if satisfies(gold_spec, trace) == satisfies(pred_spec, trace):
            matches += 1
    return matches / TRACE_COUNT


def build_spec(formula: str, variables: list[str]) -> rtamt.StlDiscreteTimeSpecification:
    spec = rtamt.StlDiscreteTimeSpecification()
    for variable in variables:
        spec.declare_var(variable, "float")
    spec.spec = formula
    spec.parse()
    return spec


def satisfies(spec: rtamt.StlDiscreteTimeSpecification, trace: dict[str, list[float]]) -> bool:
    robustness = spec.evaluate(trace)
    return bool(robustness and robustness[0][1] >= 0)


def generate_trace(
    variables: list[str],
    thresholds: list[float],
    horizon: int,
    rng: random.Random,
) -> dict[str, list[float]]:
    centers = thresholds or [0.0]
    trace: dict[str, list[float]] = {"time": list(range(horizon + 1))}
    for variable in variables:
        current = rng.uniform(min(centers) - 5.0, max(centers) + 5.0)
        values: list[float] = []
        for _ in range(horizon + 1):
            if rng.random() < 0.35:
                current = rng.choice(centers) + rng.uniform(-3.0, 3.0)
            else:
                current += rng.uniform(-1.5, 1.5)
            values.append(current)
        trace[variable] = values
    return trace


def extract_numeric_thresholds(formula: str) -> list[float]:
    pattern = rf"(?:{COMPARATOR_RE})\s*({NUMBER_RE})"
    return [float(match.group(1)) for match in re.finditer(pattern, formula)]


def discretize_intervals(formula: str) -> str:
    def replace(match: re.Match[str]) -> str:
        start = min(math.ceil(float(match.group(1))), MAX_HORIZON)
        end = min(math.floor(float(match.group(2))), MAX_HORIZON)
        return f"[{start}:{max(start, end)}]"

    return re.sub(rf"\[\s*({NUMBER_RE})\s*[:,]\s*({NUMBER_RE})\s*\]", replace, formula)


def max_interval_end(formula: str) -> int:
    pattern = rf"\[\s*{NUMBER_RE}\s*[:,]\s*({NUMBER_RE})\s*\]"
    ends = [float(match.group(1)) for match in re.finditer(pattern, formula)]
    return math.ceil(max(ends, default=0.0))


if __name__ == "__main__":
    import sys

    print(Semantic_Robustness(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
