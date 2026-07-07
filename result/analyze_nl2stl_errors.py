#!/usr/bin/env python3
"""Analyze NL->STL result files in this directory."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from STL2AST import stl2ast  # noqa: E402


RESULT_RE = re.compile(
    r"taskid:\s*(\d+),\s*\n\s*"
    r'gold_stl:"((?:\\.|[^"\\])*)",\s*\n\s*'
    r'pred_stl:"((?:\\.|[^"\\])*)",',
    flags=re.DOTALL,
)

UNARY_TEMPORAL = {"always", "eventually", "once", "historically"}
BINARY_TEMPORAL = {"until", "weak_until", "release", "since"}
TEMPORAL = UNARY_TEMPORAL | BINARY_TEMPORAL
EDGE = {"rise", "fall", "peak"}
COMPLEMENT_RELATION = {
    "<": ">=",
    "<=": ">",
    ">": "<=",
    ">=": "<",
    "==": "!=",
    "!=": "==",
}
TEMPORAL_DUAL = {
    "always": "eventually",
    "eventually": "always",
    "historically": "once",
    "once": "historically",
}


def unescape(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def load_results(path: Path) -> list[dict[str, str]]:
    rows = []
    for taskid, gold, pred in RESULT_RE.findall(path.read_text(encoding="utf-8")):
        rows.append(
            {
                "taskid": int(taskid),
                "gold_stl": unescape(gold),
                "pred_stl": unescape(pred),
            }
        )
    return rows


def load_dataset() -> dict[int, dict[str, str]]:
    dataset = REPO_ROOT / "dataset" / "deepstl_test_300_sample.csv"
    if not dataset.exists():
        return {}
    with dataset.open("r", encoding="utf-8", newline="") as f:
        return {idx: row for idx, row in enumerate(csv.DictReader(f))}


def normalize_input(text: str) -> str:
    text = str(text).strip()
    text = re.sub(
        r"\b(always|eventually|until|weak_until|release|once|historically|since)\s*_\s*\{\s*\[([^\]]+)\]\s*\}",
        lambda m: f"{m.group(1)} [{m.group(2)}]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(always|eventually|until|weak_until|release|once|historically|since)\s*_\s*\[([^\]]+)\]",
        lambda m: f"{m.group(1)} [{m.group(2)}]",
        text,
        flags=re.IGNORECASE,
    )
    return text


def parse_ast(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(stl2ast(normalize_input(text)))
    except Exception:
        return None


def norm_number(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def expr_key(expr: dict[str, Any]) -> Any:
    kind = expr.get("exprType")
    if kind == "constant":
        return ("const", norm_number(expr.get("value")))
    if kind in {"signal", "parameter"}:
        return (kind, expr.get("name"))
    if kind == "binary":
        return (
            "expr",
            expr.get("operator"),
            expr_key(expr["left"]),
            expr_key(expr["right"]),
        )
    return tuple(sorted(expr.items()))


def interval_key(interval: dict[str, Any] | None) -> tuple[Any, ...]:
    if not interval:
        return (0, "inf", True, False)
    return (
        norm_number(interval.get("lower", 0)),
        norm_number(interval.get("upper", "inf")),
        bool(interval.get("lowerInclusive", True)),
        bool(interval.get("upperInclusive", interval.get("upper") != "inf")),
    )


def make_not(child: Any) -> Any:
    if child[0] == "pred":
        relation = child[2]
        if relation in COMPLEMENT_RELATION:
            return ("pred", child[1], COMPLEMENT_RELATION[relation], child[3])
    if child[0] == "bool" and child[1] == "not":
        return child[2]
    if child[0] == "bool" and child[1] == "and":
        return normalize_bool("or", [make_not(x) for x in child[2]])
    if child[0] == "bool" and child[1] == "or":
        return normalize_bool("and", [make_not(x) for x in child[2]])
    if child[0] == "temp" and child[1] in TEMPORAL_DUAL:
        return ("temp", TEMPORAL_DUAL[child[1]], child[2], (make_not(child[3][0]),))
    return ("bool", "not", child)


def normalize_bool(op: str, operands: list[Any]) -> Any:
    normalized = []
    for operand in operands:
        if operand[0] == "bool" and operand[1] == op and op in {"and", "or"}:
            normalized.extend(operand[2])
        else:
            normalized.append(operand)
    if op in {"and", "or"}:
        normalized = sorted(normalized, key=repr)
        if len(normalized) == 1:
            return normalized[0]
        return ("bool", op, tuple(normalized))
    return ("bool", op, tuple(normalized))


def canonical(node: dict[str, Any]) -> Any:
    kind = node.get("nodeType")
    if kind == "predicate":
        return (
            "pred",
            expr_key(node["left"]),
            node.get("relation"),
            expr_key(node["right"]),
        )
    if kind == "boolean":
        op = node.get("operator")
        operands = [canonical(x) for x in node.get("operands", [])]
        if op == "not":
            return make_not(operands[0])
        return normalize_bool(op, operands)
    if kind in {"temporal", "pastTemporal"}:
        op = node.get("operator")
        operands = tuple(canonical(x) for x in node.get("operands", []))
        return ("temp", op, interval_key(node.get("interval")), operands)
    if kind == "edge":
        op = node.get("operator")
        operand = canonical(node["operand"])
        if op == "fall":
            return ("edge", "rise", make_not(operand))
        return ("edge", op, operand)
    return tuple(sorted(node.items()))


def walk_key(key: Any):
    yield key
    if not isinstance(key, tuple):
        return
    head = key[0]
    if head == "bool":
        children = key[2] if key[1] in {"and", "or"} else (key[2],)
    elif head == "temp":
        children = key[3]
    elif head == "edge":
        children = (key[2],)
    else:
        children = ()
    for child in children:
        yield from walk_key(child)


def feature_counts(key: Any) -> dict[str, Counter]:
    counts = {
        "temporal": Counter(),
        "temporal_interval": Counter(),
        "edge": Counter(),
        "boolean": Counter(),
        "predicate": Counter(),
        "signals": Counter(),
        "numbers": Counter(),
    }
    for node in walk_key(key):
        if not isinstance(node, tuple):
            continue
        if node[0] == "temp":
            counts["temporal"][node[1]] += 1
            counts["temporal_interval"][(node[1], node[2])] += 1
        elif node[0] == "edge":
            counts["edge"][node[1]] += 1
        elif node[0] == "bool":
            counts["boolean"][node[1]] += 1
        elif node[0] == "pred":
            counts["predicate"][node] += 1
            for expr in (node[1], node[3]):
                collect_expr(expr, counts)
    return counts


def collect_expr(expr: Any, counts: dict[str, Counter]) -> None:
    if not isinstance(expr, tuple):
        return
    if expr[0] == "signal":
        counts["signals"][expr[1]] += 1
    elif expr[0] == "const":
        counts["numbers"][expr[1]] += 1
    elif expr[0] == "expr":
        collect_expr(expr[2], counts)
        collect_expr(expr[3], counts)


def text_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*|<=|>=|==|!=|[<>]|\d+(?:\.\d+)?", text)


def bad_artifacts(text: str) -> list[str]:
    artifacts = []
    checks = {
        "non_stl_quantifier_or_phrase": ["forall", "within", "execution_ends"],
        "symbolic_or_placeholder_bound": ["tau", "∞"],
        "natural_language_leakage": ["可以", "STL formula", "formula is"],
        "latex_interval_notation": ["_{"],
    }
    low = text.lower()
    for label, needles in checks.items():
        if any(n.lower() in low for n in needles):
            artifacts.append(label)
    return artifacts


def classify(gold_text: str, pred_text: str, gold_key: Any, pred_key: Any | None) -> set[str]:
    labels = set()
    labels.update(bad_artifacts(pred_text))
    if pred_key is None:
        labels.add("syntax_or_parse_error")
        return labels

    g = feature_counts(gold_key)
    p = feature_counts(pred_key)

    if next(iter(gold_key), None) != next(iter(pred_key), None):
        labels.add("top_level_structure_error")

    if g["temporal"] != p["temporal"]:
        labels.add("temporal_operator_scope_error")
    elif g["temporal_interval"] != p["temporal_interval"]:
        labels.add("temporal_interval_binding_error")

    if g["edge"] != p["edge"]:
        labels.add("rise_fall_event_error")

    if g["boolean"] != p["boolean"]:
        labels.add("logical_connective_or_negation_error")

    if g["predicate"] != p["predicate"]:
        if g["signals"] != p["signals"] or g["numbers"] != p["numbers"]:
            labels.add("signal_or_threshold_error")
        labels.add("predicate_relation_or_range_error")

    if (
        gold_text.strip().lower().startswith("always")
        and not pred_text.strip().lower().startswith("always")
    ):
        labels.add("missing_outer_always")

    low = normalize_input(pred_text).lower()
    if re.search(r"\beventually\b.*\b(or|and)\b.*\beventually\b", low) or re.search(
        r"\balways\b.*\b(or|and)\b.*\balways\b", low
    ):
        labels.add("distributed_temporal_over_boolean")

    if any(op in gold_text.lower() or op in pred_text.lower() for op in ["since", "once", "historically"]):
        labels.add("past_time_operator_case")

    if not labels:
        labels.add("structural_mismatch_other")
    return labels


def pct(n: int, d: int) -> str:
    return f"{n / d * 100:.1f}%" if d else "0.0%"


def main() -> int:
    dataset = load_dataset()
    result_files = sorted(ROOT.glob("*_result.txt"))
    summary_rows = []
    type_rows = defaultdict(list)
    error_rows = {}
    examples = defaultdict(list)

    for path in result_files:
        rows = load_results(path)
        correct = 0
        parsed = 0
        exact_text = 0
        tag_counts = Counter()
        by_type = defaultdict(lambda: Counter(total=0, correct=0, parsed=0))

        for row in rows:
            taskid = int(row["taskid"])
            gold_text = row["gold_stl"]
            pred_text = row["pred_stl"]
            exact_text += normalize_for_exact(gold_text) == normalize_for_exact(pred_text)

            gold_ast = parse_ast(gold_text)
            pred_ast = parse_ast(pred_text)
            if gold_ast is None:
                raise ValueError(f"Gold STL failed to parse: {taskid}: {gold_text}")
            gold_key = canonical(gold_ast)
            pred_key = canonical(pred_ast) if pred_ast is not None else None
            is_parsed = pred_key is not None
            is_correct = pred_key == gold_key
            parsed += int(is_parsed)
            correct += int(is_correct)

            typ = dataset.get(taskid, {}).get("Type", "unknown")
            by_type[typ]["total"] += 1
            by_type[typ]["parsed"] += int(is_parsed)
            by_type[typ]["correct"] += int(is_correct)

            if not is_correct:
                labels = classify(gold_text, pred_text, gold_key, pred_key)
                tag_counts.update(labels)
                for label in labels:
                    if len(examples[(path.name, label)]) < 3:
                        examples[(path.name, label)].append(
                            {
                                "taskid": taskid,
                                "gold": gold_text,
                                "pred": pred_text,
                            }
                        )

        summary_rows.append(
            {
                "file": path.name,
                "n": len(rows),
                "parse_valid": parsed,
                "parse_valid_pct": pct(parsed, len(rows)),
                "canonical_correct": correct,
                "canonical_acc": pct(correct, len(rows)),
                "exact_norm": exact_text,
                "exact_norm_pct": pct(exact_text, len(rows)),
                "errors": len(rows) - correct,
            }
        )
        error_rows[path.name] = tag_counts
        for typ, c in sorted(by_type.items()):
            type_rows[path.name].append(
                {
                    "type": typ,
                    "n": c["total"],
                    "correct": c["correct"],
                    "acc": pct(c["correct"], c["total"]),
                    "parse_valid": c["parsed"],
                    "parse_valid_pct": pct(c["parsed"], c["total"]),
                }
            )

    print("# Summary")
    for row in summary_rows:
        print(
            f"{row['file']}: n={row['n']} parse={row['parse_valid']} ({row['parse_valid_pct']}) "
            f"canonical_correct={row['canonical_correct']} ({row['canonical_acc']}) "
            f"exact_norm={row['exact_norm']} ({row['exact_norm_pct']}) errors={row['errors']}"
        )

    print("\n# Accuracy by dataset Type")
    for file_name, rows in type_rows.items():
        print(f"\n{file_name}")
        for row in rows:
            print(
                f"  {row['type']}: {row['correct']}/{row['n']} ({row['acc']}), "
                f"parse={row['parse_valid']}/{row['n']} ({row['parse_valid_pct']})"
            )

    print("\n# Error tags, multi-label over incorrect samples")
    for file_name, counts in error_rows.items():
        print(f"\n{file_name}")
        total_errors = next(x["errors"] for x in summary_rows if x["file"] == file_name)
        for label, count in counts.most_common():
            print(f"  {label}: {count}/{total_errors} ({pct(count, total_errors)})")

    print("\n# Example errors")
    for file_name, counts in error_rows.items():
        print(f"\n{file_name}")
        for label, _count in counts.most_common(5):
            print(f"  {label}")
            for item in examples[(file_name, label)][:2]:
                print(f"    task {item['taskid']}")
                print(f"      gold: {item['gold']}")
                print(f"      pred: {item['pred']}")

    return 0


def normalize_for_exact(text: str) -> str:
    text = normalize_input(text).lower()
    text = re.sub(r"\[([^\]]+)\]", lambda m: "[" + m.group(1).replace(",", ":") + "]", text)
    text = re.sub(r"\s+", "", text)
    return text


if __name__ == "__main__":
    raise SystemExit(main())
