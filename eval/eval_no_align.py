"""直接使用原始预测计算六项 STL 指标，不执行形式对齐。

运行：../.venv/bin/python -B eval_no_align.py /path/to/result.txt
复用现有的校验、分词和计分函数；两项语义指标共享同一批轨迹。
"""

import argparse
from pathlib import Path

from bleu import bleu_for_pair
from exact_formula_match import exact_formula_match_for_pair
from formula_accuracy import formula_accuracy_for_pair
from semantic_robustness import SEED, semantic_scores_for_pair
from stl_metrics_utils import load_records, mean
from stl_syntax_validator import validate_record
from template_accuracy import template_accuracy_for_pair


TEXT_METRICS = (
    ("exact_formula_match", exact_formula_match_for_pair),
    ("formula_accuracy", formula_accuracy_for_pair),
    ("template_accuracy", template_accuracy_for_pair),
    ("bleu", bleu_for_pair),
)
METRIC_NAMES = tuple(name for name, _ in TEXT_METRICS) + (
    "semantic_robustness",
    "strict_semantic_robustness",
)


def evaluate_file(file_path: str) -> dict[str, float]:
    """预测非法计零且保留分母；标准答案非法或计算失败时抛出异常。"""
    records = load_records(file_path)
    scores = {name: [] for name in METRIC_NAMES}
    for index, record in enumerate(records):
        try:
            if validate_record(record) is not None:
                for values in scores.values():
                    values.append(0.0)
                continue

            gold, pred = record["gold_stl"], record["pred_stl"]
            for name, metric in TEXT_METRICS:
                scores[name].append(metric(gold, pred))
            semantic, strict = semantic_scores_for_pair(gold, pred, SEED + index)
            scores["semantic_robustness"].append(semantic)
            scores["strict_semantic_robustness"].append(strict)
        except Exception as error:
            raise RuntimeError(f"taskid={record['taskid']}: {type(error).__name__}: {error}") from error

    return {name: mean(values) for name, values in scores.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path", type=Path, help="结果文件路径")
    args = parser.parse_args()
    try:
        metrics = evaluate_file(str(args.file_path))
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    for name, value in metrics.items():
        print(f"{name}: {value:.6f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
