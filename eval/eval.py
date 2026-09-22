"""统一计算六项 STL 指标并输出结果。"""

import argparse
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from bleu import bleu_for_pair
from exact_formula_match import exact_formula_match_for_pair
from formula_aligner import DEFAULT_RULE_PATH, align_formula
from formula_accuracy import formula_accuracy_for_pair
from semantic_robustness import (
    MAX_HORIZON,
    SEED,
    TRACE_COUNT,
    interval_adjustments,
    semantic_scores_for_pair,
)
from stl_metrics_utils import load_records, mean
from stl_syntax_validator import validate_record
from template_accuracy import template_accuracy_for_pair

PROJECT_ROOT = Path(__file__).resolve().parent.parent
file_path = PROJECT_ROOT / "result" / "DeepSTL_with_dsl_result.txt"

METRIC_NAMES = (
    "exact_formula_match",
    "formula_accuracy",
    "template_accuracy",
    "bleu",
    "semantic_robustness",
    "strict_semantic_robustness",
)


def evaluate_file(file_path: str) -> tuple[dict, list[dict]]:
    """依次计算各项指标；预测非法计零，计算异常使汇总标记为未完成。"""
    records = load_records(file_path)
    details = []
    for record in records:
        result = {
            **record,
            "aligned_pred_stl": record["pred_stl"],
            "alignment_replacements": [],
            "status": "ok",
            "error": None,
            "scores": dict.fromkeys(METRIC_NAMES),
            "interval_adjustments": {"gold_stl": None, "pred_stl": None},
        }
        try:
            error = validate_record(record)
            gold, pred = record["gold_stl"], record["pred_stl"]
            result["interval_adjustments"]["gold_stl"] = interval_adjustments(gold)
            if error is not None:
                result["status"] = "invalid_prediction"
                result["error"] = error
                result["scores"] = dict.fromkeys(METRIC_NAMES, 0.0)
            else:
                result["interval_adjustments"]["pred_stl"] = interval_adjustments(pred)
                alignment = align_formula(gold, pred)
                result["aligned_pred_stl"] = alignment.aligned_pred_stl
                result["alignment_replacements"] = [
                    {
                        "pred_path": list(item.pred_path),
                        "gold_path": list(item.gold_path),
                        "pred_fragment": item.pred_fragment,
                        "gold_fragment": item.gold_fragment,
                    }
                    for item in alignment.replacements
                ]
        except Exception as error:
            result["status"] = "error"
            result["error"] = f"taskid={record['taskid']}: {type(error).__name__}: {error}"
        details.append(result)

    for item in details:
        if item["status"] != "ok":
            continue
        try:
            item["scores"]["exact_formula_match"] = exact_formula_match_for_pair(
                item["gold_stl"], item["aligned_pred_stl"]
            )
        except Exception as error:
            _record_error(item, error)
    _print_metric("exact_formula_match", details)

    for item in details:
        if item["status"] != "ok":
            continue
        try:
            item["scores"]["formula_accuracy"] = formula_accuracy_for_pair(
                item["gold_stl"], item["aligned_pred_stl"]
            )
        except Exception as error:
            _record_error(item, error)
    _print_metric("formula_accuracy", details)

    for item in details:
        if item["status"] != "ok":
            continue
        try:
            item["scores"]["template_accuracy"] = template_accuracy_for_pair(
                item["gold_stl"], item["aligned_pred_stl"]
            )
        except Exception as error:
            _record_error(item, error)
    _print_metric("template_accuracy", details)

    for item in details:
        if item["status"] != "ok":
            continue
        try:
            item["scores"]["bleu"] = bleu_for_pair(
                item["gold_stl"], item["aligned_pred_stl"]
            )
        except Exception as error:
            _record_error(item, error)
    _print_metric("bleu", details)

    for index, item in enumerate(details):
        if item["status"] != "ok":
            continue
        try:
            semantic, strict = semantic_scores_for_pair(
                item["gold_stl"], item["pred_stl"], SEED + index
            )
            item["scores"]["semantic_robustness"] = semantic
            item["scores"]["strict_semantic_robustness"] = strict
        except Exception as error:
            _record_error(item, error)
    _print_metric("semantic_robustness", details)
    _print_metric("strict_semantic_robustness", details)

    error_count = sum(item["status"] == "error" for item in details)
    metrics = dict.fromkeys(METRIC_NAMES)
    if error_count == 0:
        for name in METRIC_NAMES:
            metrics[name] = mean([item["scores"][name] for item in details])

    adjustment_counts = {"rounded": 0, "clipped": 0, "empty_window_adjusted": 0}
    for item in details:
        flags = item["interval_adjustments"]
        for name in adjustment_counts:
            if any(value is not None and value[name] for value in flags.values()):
                adjustment_counts[name] += 1

    summary = {
        "input_file": str(Path(file_path).resolve()),
        "metric_version": "dsl_eval_v2_alignment",
        "rtamt_version": version("rtamt"),
        "status": "complete" if error_count == 0 else "incomplete",
        "sample_count": len(records),
        "valid_prediction_count": sum(item["status"] == "ok" for item in details),
        "invalid_prediction_count": sum(item["status"] == "invalid_prediction" for item in details),
        "error_count": error_count,
        "metrics": metrics,
        "alignment": {
            "enabled": True,
            "rule_file": str(DEFAULT_RULE_PATH.resolve()),
            "aligned_sample_count": sum(
                item["status"] == "ok" and item["aligned_pred_stl"] != item["pred_stl"]
                for item in details
            ),
            "replacement_count": sum(
                len(item["alignment_replacements"]) for item in details
            ),
            "text_metrics_formula": "aligned_pred_stl",
            "semantic_metrics_formula": "pred_stl",
        },
        "semantic_settings": {
            "trace_count": TRACE_COUNT,
            "seed": SEED,
            "seed_rule": "seed + zero_based_record_index",
            "max_horizon": MAX_HORIZON,
            "interval_policy": "ceil(start), floor(end), clip to max_horizon, end=max(start,end)",
            "satisfaction_rule": "robustness at t=0 >= 0",
            "equal_tokens_shortcut": True,
            "note": "沿用旧版有限轨迹近似，取整和截断会改变时间窗口；不代表形式化等价性证明。",
        },
        "samples_with_interval_adjustments": adjustment_counts,
        "text_policy": "先按确定性等价规则将预测子树对齐为 gold 写法，再规范化 token 计分。",
    }
    return summary, details


def _record_error(item: dict, error: Exception) -> None:
    """记录单条样本的计算异常。"""
    item["status"] = "error"
    item["error"] = f"taskid={item['taskid']}: {type(error).__name__}: {error}"


def _print_metric(name: str, details: list[dict]) -> None:
    """输出刚刚计算完成的指标。"""
    scores = [item["scores"][name] for item in details]
    if any(score is None for score in scores):
        print(f"{name}: 未完成", flush=True)
        return
    print(f"{name}: {mean(scores):.6f}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path", nargs="?", type=Path, default=file_path, help="结果文件路径")
    args = parser.parse_args()
    start_time = perf_counter()
    try:
        summary, details = evaluate_file(str(args.file_path))
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(f"样本数: {summary['sample_count']}，非法预测: {summary['invalid_prediction_count']}，计算异常: {summary['error_count']}")
    alignment = summary["alignment"]
    print(f"形式对齐样本: {alignment['aligned_sample_count']}，替换子树: {alignment['replacement_count']}")
    print(f"语义采样: {TRACE_COUNT} 条轨迹，基础种子 {SEED}，最大时域 {MAX_HORIZON}")
    counts = summary["samples_with_interval_adjustments"]
    print(f"含需取整区间的样本: {counts['rounded']}，含需截断区间的样本: {counts['clipped']}，含离散空区间修正的样本: {counts['empty_window_adjusted']}")
    print("语义指标沿用旧版取整和截断规则，属于有限轨迹近似评估。")
    for item in details:
        if item["status"] == "error":
            print(item["error"])
    elapsed_time = perf_counter() - start_time
    print(f"整体耗时: {elapsed_time:.2f} 秒")
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
