"""Align semantically equivalent prediction subtrees to reference STL syntax."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from stl_ast import FormulaNode, FormulaTree, iter_nodes, parse_formula, semantic_key
from stl_syntax_validator import syntax_error


DEFAULT_RULE_PATH = Path(__file__).with_name("stl_alignment_rules.md")


@dataclass(frozen=True)
class AlignmentRule:
    text: str
    left: FormulaTree
    right: FormulaTree


@dataclass(frozen=True)
class Replacement:
    pred_path: tuple[int, ...]
    gold_path: tuple[int, ...]
    pred_fragment: str
    gold_fragment: str


@dataclass(frozen=True)
class AlignmentResult:
    original_pred_stl: str
    aligned_pred_stl: str
    replacements: tuple[Replacement, ...]


@dataclass(frozen=True)
class _NodeRef:
    path: tuple[int, ...]
    node: FormulaNode
    key: tuple


def load_alignment_rules(rule_path: str | Path = DEFAULT_RULE_PATH) -> tuple[AlignmentRule, ...]:
    """Load the rule-only Markdown file and verify every declared equivalence."""
    path = Path(rule_path)
    return _parse_alignment_rules(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def _parse_alignment_rules(content: str) -> tuple[AlignmentRule, ...]:
    """Cache compiled rules by content while still observing file changes."""
    rules: list[AlignmentRule] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.startswith("- ") or line.count("↔") != 1:
            raise ValueError(f"规则文件第 {line_number} 行格式无效")
        text = line[2:].strip()
        left_text, right_text = (part.strip() for part in text.split("↔", 1))
        left = parse_formula(left_text)
        right = parse_formula(right_text)
        if semantic_key(left.root) != semantic_key(right.root):
            raise ValueError(f"规则文件第 {line_number} 行未通过确定性等价检查：{text}")
        rules.append(AlignmentRule(text, left, right))
    if not rules:
        raise ValueError("规则文件为空")
    return tuple(rules)


def align_formula(
    gold_stl: str,
    pred_stl: str,
    rule_path: str | Path = DEFAULT_RULE_PATH,
) -> AlignmentResult:
    """Replace equivalent prediction subtrees with their gold-side syntax."""
    # Loading is part of each alignment operation by design: the external rule
    # file remains the checked source of truth instead of an ignored document.
    load_alignment_rules(rule_path)
    gold = parse_formula(gold_stl)
    pred = parse_formula(pred_stl)

    gold_refs = [
        _NodeRef(path, node, semantic_key(node))
        for path, node in iter_nodes(gold.root)
        if _eligible(node)
    ]
    refs_by_key: dict[tuple, list[_NodeRef]] = {}
    for ref in gold_refs:
        refs_by_key.setdefault(ref.key, []).append(ref)

    used_gold_spans: list[tuple[int, int]] = []
    replacements: list[tuple[FormulaNode, _NodeRef, tuple[int, ...]]] = []

    def visit(path: tuple[int, ...], node: FormulaNode) -> None:
        if _eligible(node):
            key = semantic_key(node)
            candidates = [
                candidate for candidate in refs_by_key.get(key, ())
                if not _overlaps_any(candidate.node.start, candidate.node.end, used_gold_spans)
            ]
            if candidates:
                candidate = max(candidates, key=lambda item: _match_rank(path, node, item))
                used_gold_spans.append((candidate.node.start, candidate.node.end))
                if _normalized_fragment(node.raw) != _normalized_fragment(candidate.node.raw):
                    replacements.append((node, candidate, path))
                return
        for index, child in enumerate(node.children):
            visit(path + (index,), child)

    visit((), pred.root)
    if not replacements:
        return AlignmentResult(pred_stl, pred_stl, ())

    aligned_internal = _apply_replacements(pred.text, replacements, wrap=False)
    aligned = aligned_internal.replace("!==", "!=")
    if not _is_safe_alignment(pred.root, aligned):
        aligned_internal = _apply_replacements(pred.text, replacements, wrap=True)
        aligned = aligned_internal.replace("!==", "!=")
    if not _is_safe_alignment(pred.root, aligned):
        raise ValueError("对齐后的公式未能保持预测公式语义")

    public_replacements = tuple(
        Replacement(
            pred_path=path,
            gold_path=gold_ref.path,
            pred_fragment=pred_node.raw.replace("!==", "!="),
            gold_fragment=gold_ref.node.raw.replace("!==", "!="),
        )
        for pred_node, gold_ref, path in sorted(replacements, key=lambda item: item[0].start)
    )
    return AlignmentResult(pred_stl, aligned, public_replacements)


def align_record(record: dict[str, str], rule_path: str | Path = DEFAULT_RULE_PATH) -> dict:
    result = align_formula(record["gold_stl"], record["pred_stl"], rule_path)
    return {
        **record,
        "aligned_pred_stl": result.aligned_pred_stl,
        "alignment_replacements": [
            {
                "pred_path": list(item.pred_path),
                "gold_path": list(item.gold_path),
                "pred_fragment": item.pred_fragment,
                "gold_fragment": item.gold_fragment,
            }
            for item in result.replacements
        ],
    }


def _eligible(node: FormulaNode) -> bool:
    return node.kind != "term"


def _match_rank(pred_path: tuple[int, ...], pred_node: FormulaNode, gold_ref: _NodeRef) -> tuple:
    common_prefix = 0
    for left, right in zip(pred_path, gold_ref.path):
        if left != right:
            break
        common_prefix += 1
    return (
        pred_node.kind == gold_ref.node.kind,
        common_prefix,
        -abs(len(pred_path) - len(gold_ref.path)),
        -abs(pred_node.size - gold_ref.node.size),
        -len(gold_ref.path),
        tuple(-part for part in gold_ref.path),
    )


def _overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < used_end and used_start < end for used_start, used_end in spans)


def _normalized_fragment(fragment: str) -> str:
    return " ".join(fragment.replace("!==", "!=").split())


def _apply_replacements(
    pred_text: str,
    replacements: list[tuple[FormulaNode, _NodeRef, tuple[int, ...]]],
    *,
    wrap: bool,
) -> str:
    output: list[str] = []
    cursor = 0
    for pred_node, gold_ref, _ in sorted(replacements, key=lambda item: item[0].start):
        output.append(pred_text[cursor:pred_node.start])
        fragment = gold_ref.node.raw
        if wrap and pred_node.start != 0 and gold_ref.node.kind != "group":
            fragment = f"( {fragment} )"
        output.append(fragment)
        cursor = pred_node.end
    output.append(pred_text[cursor:])
    return "".join(output)


def _is_safe_alignment(original_root: FormulaNode, aligned: str) -> bool:
    if syntax_error(aligned) is not None:
        return False
    try:
        return semantic_key(parse_formula(aligned).root) == semantic_key(original_root)
    except (TypeError, ValueError):
        return False
