#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


TARGET_OPERATORS = (
    "always",
    "eventually",
    "until",
    "since",
    "historically",
    "once",
    "rise",
    "fall",
)


DIRECT_COMBOS = {
    "not_always": r"not\s*\(?\s*always\b",
    "not_eventually": r"not\s*\(?\s*eventually\b",
    "not_until": r"not\s*\(",
    "not_since": r"not\s*\(",
    "not_historically": r"not\s*\(?\s*historically\b",
    "not_once": r"not\s*\(?\s*once\b",
    "not_rise_until": r"not\s*\(?\s*rise\s*\(",
    "not_rise_since": r"not\s*\(?\s*rise\s*\(",
    "not_rise": r"not\s*\(?\s*rise\s*\(",
    "not_fall_eventually": r"not\s*\(?\s*fall\s*\(\s*eventually\b",
    "not_fall_until": r"not\s*\(?\s*fall\s*\(",
    "not_fall_since": r"not\s*\(?\s*fall\s*\(",
    "not_fall_always": r"not\s*\(?\s*fall\s*\(\s*always\b",
    "not_fall_historically": r"not\s*\(?\s*fall\s*\(\s*historically\b",
    "not_fall": r"not\s*\(?\s*fall\s*\(",
    "not_rise_eventually": r"not\s*\(?\s*rise\s*\(\s*eventually\b",
    "always_eventually": r"\balways(?:\s*\[[^\]]+\])?\s*\(\s*eventually\b",
    "always_once": r"\balways(?:\s*\[[^\]]+\])?\s*\(\s*once\b",
    "always_historically": r"\balways(?:\s*\[[^\]]+\])?\s*\(\s*historically\b",
    "always_not_rise": r"\balways(?:\s*\[[^\]]+\])?\s*\(\s*not\s+rise\s*\(",
    "always_not_fall": r"\balways(?:\s*\[[^\]]+\])?\s*\(\s*not\s+fall\s*\(",
    "eventually_always": r"\beventually(?:\s*\[[^\]]+\])?\s*\(\s*always\b",
    "eventually_rise": r"\beventually(?:\s*\[[^\]]+\])?\s*\(\s*rise\s*\(",
    "eventually_fall": r"\beventually(?:\s*\[[^\]]+\])?\s*\(\s*fall\s*\(",
    "eventually_not_rise": r"\beventually(?:\s*\[[^\]]+\])?\s*\(\s*not\s+rise\s*\(",
    "eventually_not_fall": r"\beventually(?:\s*\[[^\]]+\])?\s*\(\s*not\s+fall\s*\(",
    "once_rise": r"\bonce(?:\s*\[[^\]]+\])?\s*\(\s*rise\s*\(",
    "once_fall": r"\bonce(?:\s*\[[^\]]+\])?\s*\(\s*fall\s*\(",
    "once_not_rise": r"\bonce(?:\s*\[[^\]]+\])?\s*\(\s*not\s+rise\s*\(",
    "once_not_fall": r"\bonce(?:\s*\[[^\]]+\])?\s*\(\s*not\s+fall\s*\(",
    "rise_always": r"\brise\s*\(\s*always\b",
    "rise_once": r"\brise\s*\(\s*once\b",
    "rise_until": r"\brise\s*\(",
    "since_rise": r"\bsince(?:\s*\[[^\]]+\])?\s*\(\s*rise\s*\(",
    "since_fall": r"\bsince(?:\s*\[[^\]]+\])?\s*\(\s*fall\s*\(",
    "since_not_fall": r"\(?\s*not\s+fall\s*\([^)]*\)\s*\)?\s*since\b|\bsince(?:\s*\[[^\]]+\])?\s*\(\s*not\s+fall\s*\(",
    "until_rise": r"\buntil(?:\s*\[[^\]]+\])?\s*\(\s*rise\s*\(",
    "until_fall": r"\buntil(?:\s*\[[^\]]+\])?\s*\(\s*fall\s*\(",
    "until_not_rise": r"\(?\s*not\s+rise\s*\([^)]*\)\s*\)?\s*until\b|\buntil(?:\s*\[[^\]]+\])?\s*\(\s*not\s+rise\s*\(",
    "until_not_fall": r"\(?\s*not\s+fall\s*\([^)]*\)\s*\)?\s*until\b|\buntil(?:\s*\[[^\]]+\])?\s*\(\s*not\s+fall\s*\(",
    "fall_always": r"\bfall\s*\(\s*always\b",
    "fall_eventually": r"\bfall\s*\(\s*eventually\b",
    "fall_once": r"\bfall\s*\(\s*once\b",
    "fall_until": r"\bfall\s*\(",
    "fall_since": r"\bfall\s*\(",
    "fall_historically": r"\bfall\s*\(\s*historically\b",
    "historically_not_rise": r"\bhistorically(?:\s*\[[^\]]+\])?\s*\(\s*not\s+rise\s*\(",
    "historically_not_fall": r"\bhistorically(?:\s*\[[^\]]+\])?\s*\(\s*not\s+fall\s*\(",
}


COMBO_CHILD_OPERATORS = {
    "always_eventually": "eventually",
    "always_once": "once",
    "always_historically": "historically",
    "always_not_rise": "not_rise",
    "always_not_fall": "not_fall",
    "eventually_always": "always",
    "eventually_rise": "rise",
    "eventually_fall": "fall",
    "eventually_not_rise": "not_rise",
    "eventually_not_fall": "not_fall",
    "not_fall_always": "always",
    "not_fall_historically": "historically",
    "not_rise_eventually": "eventually",
    "not_fall_eventually": "eventually",
    "once_rise": "rise",
    "once_fall": "fall",
    "once_not_rise": "not_rise",
    "once_not_fall": "not_fall",
    "rise_always": "always",
    "rise_once": "once",
    "since_rise": "rise",
    "since_fall": "fall",
    "since_not_fall": "not_fall",
    "until_rise": "rise",
    "until_fall": "fall",
    "fall_always": "always",
    "fall_eventually": "eventually",
    "fall_once": "once",
    "fall_historically": "historically",
    "historically_not_rise": "not_rise",
    "historically_not_fall": "not_fall",
}


POSITIVE_EVENT_OUTER_COMBOS = {
    "rise_always",
    "rise_once",
    "rise_until",
    "fall_always",
    "fall_eventually",
    "fall_once",
    "fall_until",
    "fall_since",
    "fall_historically",
}


def normalize_snippet(text: str, start: int, end: int, pad: int = 45) -> str:
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    snippet = text[left:right]
    return re.sub(r"\s+", " ", snippet).strip()


def find_matching_paren(text: str, open_pos: int) -> int | None:
    depth = 0
    for pos in range(open_pos, len(text)):
        char = text[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return pos
    return None


def is_directly_negated(stl: str, start: int) -> bool:
    pos = start - 1
    while pos >= 0 and stl[pos].isspace():
        pos -= 1
    if pos >= 0 and stl[pos] == "(":
        pos -= 1
        while pos >= 0 and stl[pos].isspace():
            pos -= 1
    return re.search(r"\bnot$", stl[:pos + 1]) is not None


def combo_is_whole_child(stl: str, combo: str, start: int) -> bool:
    if combo in POSITIVE_EVENT_OUTER_COMBOS and is_directly_negated(stl, start):
        return False
    if combo in {"not_since", "not_until"}:
        return not_wraps_top_level_temporal(stl, start, "since" if combo == "not_since" else "until")
    if combo == "not_rise_until":
        return not_event_wraps_top_level_temporal(stl, start, "rise", "until")
    if combo == "not_rise_since":
        return not_event_wraps_top_level_temporal(stl, start, "rise", "since")
    if combo == "rise_until":
        return event_wraps_top_level_temporal(stl, start, "rise", "until")
    if combo == "fall_until":
        return event_wraps_top_level_temporal(stl, start, "fall", "until")
    if combo == "not_fall_until":
        return not_event_wraps_top_level_temporal(stl, start, "fall", "until")
    if combo == "not_fall_since":
        return not_event_wraps_top_level_temporal(stl, start, "fall", "since")
    if combo == "fall_since":
        return event_wraps_top_level_temporal(stl, start, "fall", "since")
    if combo == "since_not_fall":
        return (
            not_event_is_left_operand_of_since(stl, start, "fall")
            or since_has_whole_not_event_child(stl, start, "fall")
        )
    if combo in {"until_not_rise", "until_not_fall"}:
        op = "rise" if combo == "until_not_rise" else "fall"
        return (
            not_event_is_left_operand_of_until(stl, start, op)
            or until_has_whole_not_event_child(stl, start, op)
        )

    child = COMBO_CHILD_OPERATORS.get(combo)
    if child is None:
        return True

    # Find the outer operator's child parenthesis.
    outer_open = stl.find("(", start)
    if outer_open == -1:
        return False

    pos = outer_open + 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1

    if child.startswith("not_"):
        if not stl.startswith("not", pos):
            return False
        pos += 3
        while pos < len(stl) and stl[pos].isspace():
            pos += 1
        child_op = child[4:]
    else:
        child_op = child

    if not stl.startswith(child_op, pos):
        return False

    child_open = stl.find("(", pos)
    if child_open == -1:
        return False
    child_close = find_matching_paren(stl, child_open)
    outer_close = find_matching_paren(stl, outer_open)
    if child_close is None or outer_close is None:
        return False

    between = stl[child_close + 1:outer_close].strip()
    return between == ""


def has_top_level_operator(text: str, op: str) -> bool:
    depth = 0
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and re.match(rf"\b{op}\b", text[pos:]):
            return True
        pos += 1
    return False


def not_wraps_top_level_temporal(stl: str, start: int, op: str) -> bool:
    pos = start
    if not stl.startswith("not", pos):
        return False
    pos += 3
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if pos >= len(stl) or stl[pos] != "(":
        return False
    close = find_matching_paren(stl, pos)
    if close is None:
        return False
    return has_top_level_operator(stl[pos + 1:close], op)


def event_wraps_top_level_temporal(stl: str, start: int, event_op: str, temporal_op: str) -> bool:
    pos = start
    if not stl.startswith(event_op, pos):
        return False
    open_pos = stl.find("(", pos)
    if open_pos == -1:
        return False
    close_pos = find_matching_paren(stl, open_pos)
    if close_pos is None:
        return False
    return has_top_level_operator(stl[open_pos + 1:close_pos], temporal_op)


def not_event_wraps_top_level_temporal(stl: str, start: int, event_op: str, temporal_op: str) -> bool:
    pos = start
    if not stl.startswith("not", pos):
        return False
    pos += 3
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if pos < len(stl) and stl[pos] == "(":
        pos += 1
        while pos < len(stl) and stl[pos].isspace():
            pos += 1
    return event_wraps_top_level_temporal(stl, pos, event_op, temporal_op)


def not_event_is_left_operand_of_until(stl: str, start: int, op: str) -> bool:
    pos = start
    if pos < len(stl) and stl[pos] == "(":
        pos += 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if not stl.startswith("not", pos):
        return False
    pos += 3
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if not stl.startswith(op, pos):
        return False
    open_pos = stl.find("(", pos)
    if open_pos == -1:
        return False
    close_pos = find_matching_paren(stl, open_pos)
    if close_pos is None:
        return False
    pos = close_pos + 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if pos < len(stl) and stl[pos] == ")":
        pos += 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    return stl.startswith("until", pos)


def not_event_is_left_operand_of_since(stl: str, start: int, op: str) -> bool:
    pos = start
    if pos < len(stl) and stl[pos] == "(":
        pos += 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if not stl.startswith("not", pos):
        return False
    pos += 3
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if not stl.startswith(op, pos):
        return False
    open_pos = stl.find("(", pos)
    if open_pos == -1:
        return False
    close_pos = find_matching_paren(stl, open_pos)
    if close_pos is None:
        return False
    pos = close_pos + 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if pos < len(stl) and stl[pos] == ")":
        pos += 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    return stl.startswith("since", pos)


def since_has_whole_not_event_child(stl: str, start: int, op: str) -> bool:
    match = re.match(r"since(?:\s*\[[^\]]+\])?", stl[start:])
    if not match:
        return False
    outer_open = stl.find("(", start + match.end())
    if outer_open == -1:
        return False
    pos = outer_open + 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if not stl.startswith("not", pos):
        return False
    pos += 3
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if not stl.startswith(op, pos):
        return False
    child_open = stl.find("(", pos)
    if child_open == -1:
        return False
    child_close = find_matching_paren(stl, child_open)
    outer_close = find_matching_paren(stl, outer_open)
    if child_close is None or outer_close is None:
        return False
    return stl[child_close + 1:outer_close].strip() == ""


def until_has_whole_not_event_child(stl: str, start: int, op: str) -> bool:
    match = re.match(r"until(?:\s*\[[^\]]+\])?", stl[start:])
    if not match:
        return False
    outer_open = stl.find("(", start + match.end())
    if outer_open == -1:
        return False
    pos = outer_open + 1
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if not stl.startswith("not", pos):
        return False
    pos += 3
    while pos < len(stl) and stl[pos].isspace():
        pos += 1
    if not stl.startswith(op, pos):
        return False
    child_open = stl.find("(", pos)
    if child_open == -1:
        return False
    child_close = find_matching_paren(stl, child_open)
    outer_close = find_matching_paren(stl, outer_open)
    if child_close is None or outer_close is None:
        return False
    return stl[child_close + 1:outer_close].strip() == ""


def find_candidates(stl: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    for op in TARGET_OPERATORS:
        for match in re.finditer(rf"\b{op}\b(?:\s*\[[^\]]+\])?", stl):
            candidates.append({
                "operator": op,
                "kind": "base_operator",
                "stl_snippet": normalize_snippet(stl, match.start(), match.end()),
            })

    for combo, pattern in DIRECT_COMBOS.items():
        for match in re.finditer(pattern, stl):
            if not combo_is_whole_child(stl, combo, match.start()):
                continue
            candidates.append({
                "operator": combo,
                "kind": "direct_combo",
                "stl_snippet": normalize_snippet(stl, match.start(), match.end()),
            })

    candidates.sort(key=lambda item: (item["stl_snippet"], item["operator"]))
    return candidates


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for idx, row in enumerate(rows, 1):
        row["row"] = str(idx)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract mechanical operator candidates only.")
    parser.add_argument("--csv", default="deepstl_test_300_sample.csv")
    parser.add_argument("--row", type=int, help="1-based data row to print")
    parser.add_argument("--from-row", type=int, default=1)
    parser.add_argument("--to-row", type=int)
    args = parser.parse_args()

    rows = load_rows(Path(args.csv))
    if args.row is not None:
        selected = [rows[args.row - 1]]
    else:
        start = max(args.from_row, 1)
        end = args.to_row if args.to_row is not None else len(rows)
        selected = rows[start - 1:end]

    for row in selected:
        item = {
            "row": int(row["row"]),
            "type": row["Type"],
            "stl": row["STL"],
            "english": row["English"],
            "candidates": find_candidates(row["STL"]),
        }
        print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    main()
