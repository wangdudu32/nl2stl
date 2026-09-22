"""STL 评估共用的文件读取、分词和计分工具。"""

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
NUMBER_RE = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def load_records(file_path: str) -> list[Record]:
    """读取 JSON 或现有结果模板，缺失字段和重复编号直接报错。"""
    text = _strip_json_comments(_read_text(file_path))
    if not text.strip():
        raise ValueError(f"结果文件为空：{file_path}")
    parsed = _try_parse_structured(text)
    if parsed is None:
        raise ValueError(f"无法解析结果文件，请检查括号、引号和逗号：{file_path}")
    return _records_from_structured(parsed)


def _read_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8-sig") as f:
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
        except json.JSONDecodeError:
            pass
        try:
            return ast.literal_eval(candidate)
        except (ValueError, SyntaxError):
            pass
    return None


def _template_to_json_like(text: str) -> str:
    """转换外层花括号、未加引号的字段名和末尾逗号，保留字符串正文。"""
    converted = text.strip()
    converted = re.sub(r"^\{\s*\{", "[{", converted, flags=re.DOTALL)
    converted = re.sub(r"\}\s*\}\s*$", "}]", converted, flags=re.DOTALL)
    parts = re.split(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''', converted)
    for index in range(0, len(parts), 2):
        part = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', parts[index])
        parts[index] = re.sub(r",\s*([}\]])", r"\1", part)
    return "".join(parts)


def _records_from_structured(obj: Any) -> list[Record]:
    if isinstance(obj, dict):
        if "data" in obj:
            obj = obj["data"]
        elif all(isinstance(v, dict) for v in obj.values()):
            obj = list(obj.values())
        else:
            obj = [obj]

    if not isinstance(obj, list) or not obj:
        raise ValueError("结果文件必须包含至少一条评估记录")

    records: list[Record] = []
    taskids: set[str] = set()
    for index, item in enumerate(obj):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index + 1} 条记录必须是字典")
        taskid = item.get("taskid", index)
        if isinstance(taskid, bool) or not isinstance(taskid, (str, int)) or not str(taskid).strip():
            raise ValueError(f"第 {index + 1} 条记录的 taskid 无效")
        taskid = str(taskid).strip()
        if taskid in taskids:
            raise ValueError(f"taskid={taskid} 重复")
        taskids.add(taskid)
        if "gold_stl" not in item or "pred_stl" not in item:
            raise ValueError(f"taskid={taskid} 缺少 gold_stl 或 pred_stl")
        if not isinstance(item["gold_stl"], str):
            raise ValueError(f"taskid={taskid} 的 gold_stl 必须是字符串")
        pred = item["pred_stl"]
        # JSON null 与空预测一样按失败预测保留，不能从分母中移除。
        if pred is None:
            pred = ""
        if not isinstance(pred, str):
            raise ValueError(f"taskid={taskid} 的 pred_stl 必须是字符串或 null")
        record: Record = {
            "taskid": taskid,
            "gold_stl": item["gold_stl"],
            "pred_stl": pred,
        }
        records.append(record)
    return records



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
        "≤": "<=",
        "≥": ">=",
        "□": "always",
        "◇": "eventually",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"!(?!=)", " NOT ", text)

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
    text = re.sub(rf"\[\s*({NUMBER_RE})\s*,\s*({NUMBER_RE})\s*\]", r"[\1:\2]", text)
    return text


TOKEN_RE = re.compile(
    r"<=|>=|==|!=|"
    r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|"
    r"[()\[\],:!<>+=*/-]|"
    r"[^\W\d]\w*(?:\.[^\W\d]\w*)*"
)


def tokenize_formula(formula: str) -> list[str]:
    """分词时检查所有字符，避免把不支持的内容静默丢弃。"""
    text = normalize_formula(formula)
    tokens: list[str] = []
    end = 0
    for match in TOKEN_RE.finditer(text):
        if text[end:match.start()].strip():
            raise ValueError(f"无法识别的 STL 内容：{text[end:match.start()]!r}")
        tokens.append(match.group())
        end = match.end()
    if text[end:].strip():
        raise ValueError(f"无法识别的 STL 内容：{text[end:]!r}")

    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        # 仅合并一元正负号，保留 x - 1 中的减法运算符。
        previous = tokens[index - 1] if index else ""
        if (token in {"+", "-"} and index + 1 < len(tokens)
                and is_number(tokens[index + 1])
                and (index == 0 or previous in COMPARATORS | {"(", "[", ",", ":", "+", "-", "*", "/"})):
            index += 1
            token += tokens[index]
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
        index += 1
    return normalized


def is_number(token: str) -> bool:
    try:
        return Decimal(str(token)).is_finite()
    except InvalidOperation:
        return False


def normalize_number(token: str) -> str:
    try:
        value = Decimal(str(token))
    except InvalidOperation:
        return token
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


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
    return re.fullmatch(r"[^\W\d]\w*(?:\.[^\W\d]\w*)*", token) is not None


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
