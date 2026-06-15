from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .knowledge import KnowledgeBase


_FORMULA_RESERVED = {
    "always",
    "eventually",
    "historically",
    "once",
    "until",
    "weak_until",
    "release",
    "since",
    "rise",
    "fall",
    "peak",
    "and",
    "or",
    "not",
    "implies",
    "iff",
    "true",
    "false",
    "inf",
    "g",
    "f",
    "h",
    "s",
    "m",
    "km",
}


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def canonical_candidate(candidate: dict[str, Any]) -> str:
    """规范化候选文本，使空白、符号和常见单位写法不影响去重。"""

    raw = candidate.get("canonical") or candidate.get("value", "")
    raw = raw.lower().replace("≤", "<=").replace("≥", ">=")
    raw = re.sub(r"\s+", "", raw)
    raw = raw.replace("公里每小时", "km/h").replace("秒", "s")
    return raw


def rule_filter_candidates(
    candidates: list[dict[str, Any]],
    valid_local_sources: set[str] | dict[str, str],
    valid_urls: set[str] | dict[str, str],
    allowed_signals: set[str] | None = None,
    required_signals: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """确定性检查候选公式、来源真实性、数值证据和语义重复。"""

    accepted: list[dict[str, Any]] = []
    rejected: list[str] = []
    seen: set[str] = set()
    semantic_seen: set[str] = set()
    for item in candidates:
        candidate_id = item.get("id", "unknown")
        value = item.get("value", "")
        source_type = item.get("source_type")
        reference = item.get("source_reference", "")
        canonical = canonical_candidate(item)
        semantic_key = canonical.replace("<=", "<").replace(">=", ">")
        if not re.search(r"(?:<=|>=|==|!=|<|>|(?<![<>=])=(?!=))", value):
            rejected.append(f"{candidate_id}: 不是可直接执行的比较或计算公式")
            continue
        if re.search(r"(?:或者|或以|小型车.*大型车|大型车.*小型车)", value):
            rejected.append(f"{candidate_id}: 包含多个互斥方案，不能作为单一候选")
            continue
        formula_names = _formula_identifiers(value)
        if allowed_signals is not None:
            unknown = formula_names - {name.lower() for name in allowed_signals}
            if unknown:
                rejected.append(
                    f"{candidate_id}: 使用了未定义信号或参数: {', '.join(sorted(unknown))}"
                )
                continue
        if required_signals and not (
            formula_names & {name.lower() for name in required_signals}
        ):
            rejected.append(f"{candidate_id}: 没有直接回答当前待澄清谓词")
            continue
        if len(re.findall(r"(?:<=|>=|==|!=|<|>|(?<![<>=])=(?!=))", value)) > 1:
            rejected.append(f"{candidate_id}: 包含多个公式，不能作为单一候选")
            continue
        if canonical in seen or semantic_key in semantic_seen:
            rejected.append(f"{candidate_id}: 与已有候选重复")
            continue
        local_source_ids = set(valid_local_sources)
        search_source_ids = set(valid_urls)
        source_is_valid = reference in local_source_ids or any(
            reference.startswith(source + "#") for source in local_source_ids
        )
        if source_type == "knowledge_base" and not source_is_valid:
            rejected.append(f"{candidate_id}: 本地来源无法核验")
            continue
        if source_type == "knowledge_base" and isinstance(valid_local_sources, dict):
            evidence = _matching_evidence(reference, valid_local_sources)
            if not _numbers_supported(value, evidence):
                rejected.append(f"{candidate_id}: 数值未被所引知识条目支持")
                continue
        if source_type == "search" and reference not in search_source_ids:
            rejected.append(f"{candidate_id}: 搜索来源 URL 无法核验")
            continue
        if source_type == "search" and isinstance(valid_urls, dict):
            if not _numbers_supported(value, valid_urls.get(reference, "")):
                rejected.append(f"{candidate_id}: 数值未被所引搜索结果支持")
                continue
        if source_type == "llm_generated" and not reference:
            item["source_reference"] = "LLM 生成，待用户确认"
        item["canonical"] = canonical
        seen.add(canonical)
        semantic_seen.add(semantic_key)
        accepted.append(item)
    return accepted[:3], rejected


def _matching_evidence(reference: str, evidence: dict[str, str]) -> str:
    if reference in evidence:
        return evidence[reference]
    return "\n".join(
        text for source, text in evidence.items() if reference.startswith(source + "#")
    )


def _numbers_supported(value: str, evidence: str) -> bool:
    """防止候选把证据中不存在的数值冒充为知识库或搜索结论。"""

    requested = set(re.findall(r"(?<![A-Za-z_])\d+(?:\.\d+)?", value))
    if not requested:
        return True
    available = set(re.findall(r"(?<![A-Za-z_])\d+(?:\.\d+)?", evidence))
    return requested <= available


def enforce_semantic_completeness(
    semantics: dict[str, Any], original_text: str, knowledge: KnowledgeBase
) -> dict[str, Any]:
    """把模型伪装成 resolved 的未绑定符号参数恢复为待澄清状态。"""

    known_signals = knowledge.all_signal_names()
    original_lower = original_text.lower()
    unresolved: dict[str, list[dict[str, Any]]] = {}

    for item in semantics.get("items", []):
        if not isinstance(item, dict) or item.get("status") != "resolved":
            continue
        fragment = str(item.get("stl_fragment", ""))
        for name in _formula_identifiers(fragment) - known_signals:
            # An exact identifier in the NL means the user intentionally requested
            # a symbolic parameter. Natural-language concepts must be quantified.
            if name.lower() in original_lower:
                continue
            unresolved.setdefault(name, []).append(item)

    existing = {
        ambiguity.get("id")
        for ambiguity in semantics.get("ambiguities", [])
        if isinstance(ambiguity, dict)
    }
    semantics["ambiguities"] = [
        ambiguity
        for ambiguity in semantics.get("ambiguities", [])
        if not (
            isinstance(ambiguity, dict)
            and str(ambiguity.get("id", "")).startswith("unbound_parameter_")
            and str(ambiguity.get("id", "")).removeprefix("unbound_parameter_")
            not in unresolved
        )
    ]
    existing = {
        ambiguity.get("id")
        for ambiguity in semantics.get("ambiguities", [])
        if isinstance(ambiguity, dict)
    }
    for name, items in unresolved.items():
        for item in items:
            item["status"] = "pending"
        for mapping in semantics.get("mappings", []):
            if isinstance(mapping, dict) and name in str(mapping.get("stl_fragment", "")):
                mapping["status"] = "pending"

        ambiguity_id = f"unbound_parameter_{name}"
        if ambiguity_id in existing:
            continue
        nl_fragment = str(items[0].get("nl_fragment", name))
        category = _parameter_category(name)
        semantics.setdefault("ambiguities", []).append(
            {
                "id": ambiguity_id,
                "nl_fragment": nl_fragment,
                "category": category,
                "description": f"{nl_fragment} 尚未量化，参数 {name} 没有具体数值或计算公式",
                "question": (
                    f"请为“{nl_fragment}”给出具体数值、单位或计算公式；"
                    f"若要保留外部参数，请明确使用参数名 {name}。"
                ),
            }
        )
        existing.add(ambiguity_id)

    has_pending = any(
        isinstance(item, dict) and item.get("status") == "pending"
        for item in semantics.get("items", [])
    )
    semantics["is_clear"] = not semantics.get("ambiguities") and not has_pending
    return semantics


def _formula_identifiers(text: str) -> set[str]:
    text = re.sub(r"(['\"]).*?\1", " ", text)
    identifiers = {
        name.lower() for name in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text)
    }
    return identifiers - _FORMULA_RESERVED


def normalize_global_semantics(semantics: dict[str, Any]) -> dict[str, Any]:
    """修复兼容网关常见的字段枚举漂移，不改变实际语义。"""

    semantics.setdefault("revision", 0)
    semantics.setdefault("summary", "")
    semantics.setdefault("is_clear", False)
    semantics.setdefault("items", [])
    semantics.setdefault("ambiguities", [])
    semantics.setdefault("mappings", [])

    kind_aliases = {
        "definition": "predicate",
        "parameter": "other",
        "formula": "predicate",
        "condition": "predicate",
        "mapping": "other",
    }
    allowed_kinds = {
        "scope",
        "signal",
        "predicate",
        "temporal",
        "trigger",
        "logic",
        "unit",
        "other",
    }
    allowed_sources = {
        "original_nl",
        "user",
        "knowledge_base",
        "search",
        "llm_inference",
    }
    for index, item in enumerate(semantics.get("items", [])):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "other"))
        item["kind"] = kind_aliases.get(kind, kind if kind in allowed_kinds else "other")
        if item.get("source") not in allowed_sources:
            item["source"] = "user"
        item.setdefault("id", f"item_{index + 1}")
        item.setdefault("nl_fragment", str(item.get("description", item.get("value", ""))))
        item.setdefault("value", str(item.get("stl_fragment", "")))
        item.setdefault("stl_fragment", str(item.get("value", "")))
        item.setdefault("status", "resolved")
        for extra in set(item) - {
            "id",
            "nl_fragment",
            "kind",
            "value",
            "stl_fragment",
            "status",
            "source",
        }:
            item.pop(extra, None)
    allowed_categories = {
        "signal",
        "threshold",
        "unit",
        "time",
        "scope",
        "trigger",
        "operator",
        "other",
    }
    for index, ambiguity in enumerate(semantics.get("ambiguities", [])):
        if not isinstance(ambiguity, dict):
            continue
        ambiguity.setdefault("id", f"ambiguity_{index + 1}")
        ambiguity.setdefault("nl_fragment", str(ambiguity.get("description", "")))
        category = str(ambiguity.get("category", "other"))
        ambiguity["category"] = category if category in allowed_categories else "other"
        ambiguity.setdefault("description", str(ambiguity.get("nl_fragment", "")))
        ambiguity.setdefault("question", f"请澄清“{ambiguity['nl_fragment']}”。")
        for extra in set(ambiguity) - {
            "id",
            "nl_fragment",
            "category",
            "description",
            "question",
        }:
            ambiguity.pop(extra, None)
    for mapping in semantics.get("mappings", []):
        if not isinstance(mapping, dict):
            continue
        mapping.setdefault("nl_fragment", "")
        mapping.setdefault("stl_fragment", "")
        mapping.setdefault("status", "resolved")
        for extra in set(mapping) - {"nl_fragment", "stl_fragment", "status"}:
            mapping.pop(extra, None)
    return semantics


def _parameter_category(name: str) -> str:
    if any(token in name for token in ("threshold", "distance", "limit", "margin")):
        return "threshold"
    if any(token in name for token in ("time", "duration", "window", "interval")):
        return "time"
    if any(token in name for token in ("edge", "trigger")):
        return "trigger"
    return "other"


def validate_ast(ast: dict[str, Any], knowledge: KnowledgeBase) -> list[str]:
    """在 JSON Schema 之外补充未知信号和非法时间区间检查。"""

    errors = [
        f"{error.message} (path: {list(error.path)})"
        for error in Draft202012Validator(knowledge.ast_schema).iter_errors(ast)
    ]
    known = knowledge.all_signal_names()

    def walk(value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            if value.get("exprType") == "signal" and value.get("name") not in known:
                errors.append(f"未知信号 {value.get('name')} (path: {path})")
            interval = value.get("interval")
            if isinstance(interval, dict):
                lower, upper = interval.get("lower"), interval.get("upper")
                if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
                    if lower > upper:
                        errors.append(f"时间区间下界大于上界 (path: {path}.interval)")
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(ast)
    return list(dict.fromkeys(errors))


def validate_ast_against_semantics(
    ast: dict[str, Any],
    global_semantics: dict[str, Any],
    knowledge: KnowledgeBase,
) -> list[str]:
    """禁止 AST 使用当前全局语义没有声明的知识库信号。"""

    known = knowledge.all_signal_names()
    allowed: set[str] = set()
    allowed_parameters: set[str] = set()
    for item in global_semantics.get("items", []):
        if item.get("status") != "resolved":
            continue
        text = " ".join(
            str(item.get(key, ""))
            for key in ("value", "stl_fragment")
        )
        allowed.update(_known_identifiers(text, known))
        allowed_parameters.update(_formula_identifiers(text) - known)
    for mapping in global_semantics.get("mappings", []):
        if mapping.get("status") == "resolved":
            allowed.update(
                _known_identifiers(str(mapping.get("stl_fragment", "")), known)
            )

    used: set[str] = set()
    used_parameters: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("exprType") == "signal":
                used.add(str(value.get("name", "")))
            if value.get("exprType") == "parameter":
                used_parameters.add(str(value.get("name", "")).lower())
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(ast)
    errors = []
    if not allowed and used:
        errors.append("当前全局语义没有声明任何可用于 AST 的信号")
    errors.extend(
        f"AST 信号 {name} 未在当前全局语义中声明"
        for name in sorted(used - allowed)
    )
    errors.extend(
        f"AST 参数 {name} 未在已解析的全局语义中声明"
        for name in sorted(used_parameters - allowed_parameters)
    )
    return errors


def _known_identifiers(text: str, known: set[str]) -> set[str]:
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))
    return identifiers & known


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """通过同目录临时文件原子写入，避免留下半截 AST。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json_text(data) + "\n", encoding="utf-8")
    temporary.replace(path)
