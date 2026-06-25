"""Shared helpers for STL evaluation metric scripts."""

from __future__ import annotations

import ast
import json
import math
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any


Record = dict[str, str]

RESERVED_TOKENS = {
    "always",
    "eventually",
    "until",
    "weak_until",
    "release",
    "once",
    "historically",
    "since",
    "rise",
    "fall",
    "peak",
    "NOT",
    "AND",
    "OR",
    "IMPLIES",
    "IFF",
    "(",
    ")",
    "[",
    "]",
    ",",
}

COMPARATORS = {"<", "<=", ">", ">=", "==", "!=", "="}


def load_records(file_path: str) -> list[Record]:
    """Load records containing gold_stl and pred_stl from JSON or template text."""
    text = _strip_json_comments(_read_text(file_path))
    parsed = _try_parse_structured(text)
    if parsed is not None:
        records = _records_from_structured(parsed)
        if records:
            return records

    records: list[Record] = []
    for block in re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL):
        gold = _extract_field(block, "gold_stl")
        pred = _extract_field(block, "pred_stl")
        if gold is not None and pred is not None:
            taskid = _extract_field(block, "taskid")
            item: Record = {"gold_stl": gold, "pred_stl": pred}
            if taskid is not None:
                item["taskid"] = taskid
            records.append(item)
    return records


def _read_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _strip_json_comments(text: str) -> str:
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def _try_parse_structured(text: str) -> Any | None:
    candidates = [text]
    converted = _template_to_json_like(text)
    if converted != text:
        candidates.append(converted)

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            pass
        try:
            return ast.literal_eval(candidate)
        except Exception:
            pass
    return None


def _template_to_json_like(text: str) -> str:
    """Convert the documented template into a JSON-like list when possible."""
    converted = text.strip()
    converted = re.sub(r"\.\.\.\s*,?", "", converted)
    converted = re.sub(r"^\{\s*\{", "[{", converted, flags=re.DOTALL)
    converted = re.sub(r"\}\s*\}\s*$", "}]", converted, flags=re.DOTALL)
    converted = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', converted)
    converted = re.sub(r",\s*([}\]])", r"\1", converted)
    return converted


def _records_from_structured(obj: Any) -> list[Record]:
    if isinstance(obj, dict):
        if "data" in obj:
            obj = obj["data"]
        elif all(isinstance(v, dict) for v in obj.values()):
            obj = list(obj.values())
        else:
            obj = [obj]

    if not isinstance(obj, list):
        return []

    records: list[Record] = []
    for item in obj:
        if not isinstance(item, dict):
            continue
        if "gold_stl" not in item or "pred_stl" not in item:
            continue
        record: Record = {
            "gold_stl": str(item["gold_stl"]),
            "pred_stl": str(item["pred_stl"]),
        }
        if "taskid" in item:
            record["taskid"] = str(item["taskid"])
        records.append(record)
    return records


def _extract_field(block: str, field_name: str) -> str | None:
    pattern = re.compile(
        rf"{re.escape(field_name)}\s*:\s*"
        rf"(?P<dq>\"(?:\\.|[^\"\\])*\")|"
        rf"{re.escape(field_name)}\s*:\s*(?P<sq>'(?:\\.|[^'\\])*')|"
        rf"{re.escape(field_name)}\s*:\s*(?P<raw>[^,\n}}]+)",
        flags=re.DOTALL,
    )
    match = pattern.search(block)
    if not match:
        return None
    value = match.group("dq") or match.group("sq")
    if value is not None:
        try:
            return ast.literal_eval(value)
        except Exception:
            return value[1:-1]
    raw = match.group("raw")
    return raw.strip() if raw is not None else None


def normalize_formula(formula: str) -> str:
    text = str(formula).strip()
    replacements = {
        "↔": " IFF ",
        "<->": " IFF ",
        "→": " IMPLIES ",
        "⇒": " IMPLIES ",
        "=>": " IMPLIES ",
        "->": " IMPLIES ",
        "∧": " AND ",
        "&&": " AND ",
        "&": " AND ",
        "∨": " OR ",
        "||": " OR ",
        "|": " OR ",
        "¬": " NOT ",
        "!": " NOT ",
        "≤": "<=",
        "≥": ">=",
        "□": "always",
        "◇": "eventually",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    temporal_aliases = {
        "always": "always",
        "eventually": "eventually",
        "until": "until",
        "weak_until": "weak_until",
        "release": "release",
        "once": "once",
        "historically": "historically",
        "since": "since",
        "rise": "rise",
        "fall": "fall",
        "peak": "peak",
    }
    for src, dst in temporal_aliases.items():
        text = re.sub(rf"\b{re.escape(src)}\b", dst, text, flags=re.IGNORECASE)

    boolean_aliases = {
        "AND": "AND",
        "OR": "OR",
        "NOT": "NOT",
        "IMPLIES": "IMPLIES",
        "IFF": "IFF",
    }
    for src, dst in boolean_aliases.items():
        text = re.sub(rf"\b{src}\b", dst, text, flags=re.IGNORECASE)

    interval_ops = r"(always|eventually|until|weak_until|release|once|historically|since)"
    text = re.sub(rf"\b{interval_ops}\s*_\s*\{{\s*\[([^\]]+)\]\s*\}}", r"\1 [ \2 ]", text)
    text = re.sub(rf"\b{interval_ops}\s*_\s*\[([^\]]+)\]", r"\1 [ \2 ]", text)
    text = re.sub(rf"\b{interval_ops}\s*\[\s*([^\]]+)\s*\]", r"\1 [ \2 ]", text)
    return text


TOKEN_RE = re.compile(
    r"<=|>=|==|!=|"
    r"(?<![A-Za-z0-9_.])[-+]\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|"
    r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|"
    r"[()\[\],:!<>+=*/-]|"
    r"[A-Za-z_][A-Za-z0-9_./]*"
)


def tokenize_formula(formula: str) -> list[str]:
    tokens = TOKEN_RE.findall(normalize_formula(formula))
    normalized: list[str] = []
    for token in tokens:
        if token in {"=", "=="}:
            normalized.append("==")
        elif token.upper() in {"AND", "OR", "NOT", "IMPLIES", "IFF"}:
            normalized.append(token.upper())
        elif token.lower() in RESERVED_TOKENS:
            normalized.append(token.lower())
        elif is_number(token):
            normalized.append(normalize_number(token))
        else:
            normalized.append(token)
    return normalized


def is_number(token: str) -> bool:
    try:
        Decimal(str(token))
        return True
    except InvalidOperation:
        return False


def normalize_number(token: str) -> str:
    try:
        value = Decimal(str(token))
    except InvalidOperation:
        return token
    if value == value.to_integral():
        return str(value.quantize(Decimal(1)))
    return format(value.normalize(), "f")


def positional_accuracy(gold_tokens: list[str], pred_tokens: list[str]) -> float:
    denominator = max(len(gold_tokens), len(pred_tokens))
    if denominator == 0:
        return 0.0
    matches = sum(
        1 for idx, gold_token in enumerate(gold_tokens)
        if idx < len(pred_tokens) and pred_tokens[idx] == gold_token
    )
    return matches / denominator


def template_tokens(formula: str) -> list[str]:
    tokens = tokenize_formula(formula)
    result: list[str] = []
    predicate_ids: dict[tuple[str, ...], str] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if _is_interval_at(tokens, i):
            result.append("I")
            i += 5
            continue
        if _is_predicate_at(tokens, i):
            end = _predicate_end_index(tokens, i)
            result.append(_predicate_id(tuple(tokens[i:end]), predicate_ids))
            i = end
            continue
        if _is_identifier(token) and token not in RESERVED_TOKENS:
            result.append(_predicate_id((token,), predicate_ids))
            i += 1
            continue
        result.append(token)
        i += 1
    return result


def _is_interval_at(tokens: list[str], index: int) -> bool:
    return (
        index + 4 < len(tokens)
        and tokens[index] == "["
        and is_number(tokens[index + 1])
        and tokens[index + 2] in {",", ":"}
        and is_number(tokens[index + 3])
        and tokens[index + 4] == "]"
    )


def _is_predicate_at(tokens: list[str], index: int) -> bool:
    return (
        index + 2 < len(tokens)
        and _is_identifier(tokens[index])
        and tokens[index + 1] in COMPARATORS
        and (is_number(tokens[index + 2]) or _is_identifier(tokens[index + 2]))
    )


def _predicate_end_index(tokens: list[str], index: int) -> int:
    end = index + 3
    while end < len(tokens):
        token = tokens[end]
        if token in {")", "AND", "OR", "IMPLIES", "IFF", "until", "weak_until", "release", "since"}:
            break
        if token in {"(", "[", "]", ",", ":"} or token in COMPARATORS:
            break
        end += 1
    return end


def _predicate_id(predicate_key: tuple[str, ...], predicate_ids: dict[tuple[str, ...], str]) -> str:
    if predicate_key not in predicate_ids:
        predicate_ids[predicate_key] = f"P_{len(predicate_ids) + 1}"
    return predicate_ids[predicate_key]


def _is_identifier(token: str) -> bool:
    return re.match(r"^[A-Za-z_][A-Za-z0-9_./]*$", token) is not None


def bleu_score(gold_tokens: list[str], pred_tokens: list[str], max_n: int = 4) -> float:
    if not gold_tokens or not pred_tokens:
        return 0.0

    order = max(1, min(max_n, len(gold_tokens), len(pred_tokens)))
    precisions: list[float] = []
    for n in range(1, order + 1):
        pred_ngrams = _ngrams(pred_tokens, n)
        gold_ngrams = _ngrams(gold_tokens, n)
        total = sum(pred_ngrams.values())
        if total == 0:
            return 0.0
        clipped = sum(min(count, gold_ngrams[gram]) for gram, count in pred_ngrams.items())
        if n == 1:
            precision = clipped / total if total else 0.0
        else:
            precision = (clipped + 1) / (total + 1)
        if precision <= 0:
            return 0.0
        precisions.append(precision)

    bp = 1.0
    if len(pred_tokens) < len(gold_tokens):
        bp = math.exp(1 - len(gold_tokens) / len(pred_tokens))
    return bp * math.exp(sum(math.log(p) for p in precisions) / order)


def _ngrams(tokens: list[str], n: int) -> Counter[tuple[str, ...]]:
    return Counter(tuple(tokens[i:i + n]) for i in range(0, len(tokens) - n + 1))


def mean(scores: list[float]) -> float:
    return sum(scores) / len(scores) if scores else 0.0
