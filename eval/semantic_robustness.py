"""Semantic Robustness metric for STL formulas."""

from __future__ import annotations

import math
import random
import re

import rtamt

from stl_metrics_utils import NUMBER_RE, load_records, mean, normalize_formula, tokenize_formula
from stl_syntax_validator import build_spec, extract_variables, validate_record

DATASET_PATH = "data.txt"
TRACE_COUNT = 10
MAX_HORIZON = 200
SEED = 13

COMPARATOR_RE = r"<=|>=|==|!=|(?<![-<>=])<(?![-=>])|(?<![-<>=])>(?!=)|(?<![<>=])=(?![=>])"
INTERVAL_RE = re.compile(rf"\[\s*({NUMBER_RE})\s*[:,]\s*({NUMBER_RE})\s*\]")


def Semantic_Robustness(file_path: str) -> float:
    """返回各样本在随机轨迹上满足性一致比例的平均值。"""
    scores: list[float] = []
    for index, record in enumerate(load_records(file_path)):
        pred_formula = record["pred_stl"]
        if validate_record(record) is not None:
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
    """保留原有单条指标接口，计算逻辑与严格指标共用。"""
    score, _ = semantic_scores_for_pair(gold_formula, pred_formula, seed)
    return score


def semantic_scores_for_pair(gold_formula: str, pred_formula: str, seed: int) -> tuple[float, float]:
    """一批轨迹同时计算普通与严格语义分数，输入应已通过语法校验。"""
    if tokenize_formula(gold_formula) == tokenize_formula(pred_formula):
        return 1.0, 1.0

    variables = sorted(extract_variables(gold_formula) | extract_variables(pred_formula))
    if not variables:
        return 0.0, 0.0

    gold_formula = discretize_intervals(normalize_formula(gold_formula))
    pred_formula = discretize_intervals(normalize_formula(pred_formula))
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
    return matches / TRACE_COUNT, float(matches == TRACE_COUNT)


def satisfies(spec: rtamt.StlDiscreteTimeSpecification, trace: dict[str, list[float]]) -> bool:
    robustness = spec.evaluate(trace)
    if not robustness or math.isnan(robustness[0][1]):
        raise ValueError("RTAMT 未返回有效的初始时刻鲁棒值")
    return robustness[0][1] >= 0


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
    """保留旧口径：下界上取整、上界下取整、截断到 200，并修正空区间。"""
    def replace(match: re.Match[str]) -> str:
        start = min(math.ceil(float(match.group(1))), MAX_HORIZON)
        end = min(math.floor(float(match.group(2))), MAX_HORIZON)
        return f"[{start}:{max(start, end)}]"

    return INTERVAL_RE.sub(replace, formula)


def interval_adjustments(formula: str) -> dict[str, bool]:
    """报告单条公式是否含取整、截断，以及离散后空区间的修正。"""
    flags = {"rounded": False, "clipped": False, "empty_window_adjusted": False}
    for match in INTERVAL_RE.finditer(normalize_formula(formula)):
        start, end = float(match.group(1)), float(match.group(2))
        flags["rounded"] |= not start.is_integer() or not end.is_integer()
        flags["clipped"] |= start > MAX_HORIZON or end > MAX_HORIZON
        flags["empty_window_adjusted"] |= min(math.ceil(start), MAX_HORIZON) > min(math.floor(end), MAX_HORIZON)
    return flags


def max_interval_end(formula: str) -> int:
    pattern = rf"\[\s*{NUMBER_RE}\s*[:,]\s*({NUMBER_RE})\s*\]"
    ends = [float(match.group(1)) for match in re.finditer(pattern, formula)]
    return math.ceil(max(ends, default=0.0))


if __name__ == "__main__":
    import sys

    print(Semantic_Robustness(sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH))
