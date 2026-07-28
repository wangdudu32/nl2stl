"""Semantic validation and RTAMT compilation for the project STL AST."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from AST2STL import ast2stl


Ast = dict[str, Any]
SymbolTable = Mapping[str, Mapping[str, Any]]
EQUALITY_RELATIONS = {"==", "!="}
NUMERIC_RELATIONS = {"<", "<=", ">", ">=", "==", "!="}


@dataclass(frozen=True)
class ScalarType:
    kind: str
    enum_type: str | None = None
    unit: str | None = None


def _ast_object(ast: str | Mapping[str, Any]) -> Ast:
    return json.loads(ast) if isinstance(ast, str) else copy.deepcopy(dict(ast))


def _metadata_type(metadata: Mapping[str, Any]) -> ScalarType:
    raw_type = str(metadata.get("type", "")).lower()
    if raw_type == "bool":
        return ScalarType("boolean")
    if raw_type == "enum":
        return ScalarType(
            "enum",
            str(metadata.get("enum_type") or metadata.get("name") or ""),
        )
    if raw_type in {"float", "int", "number", "numeric"}:
        return ScalarType("number", unit=metadata.get("unit"))
    raise ValueError(f"unsupported signal type: {metadata.get('type')!r}")


def _enum_values(metadata: Mapping[str, Any]) -> dict[str, int]:
    values = metadata.get("enum_values", {})
    if isinstance(values, Mapping):
        return {str(name): int(code) for name, code in values.items()}
    return {str(name): index for index, name in enumerate(values)}


def _enum_metadata(symbols: SymbolTable, enum_type: str) -> Mapping[str, Any] | None:
    for name, metadata in symbols.items():
        if str(metadata.get("type", "")).lower() != "enum":
            continue
        candidate = str(metadata.get("enum_type") or metadata.get("name") or name)
        if candidate == enum_type:
            return metadata
    return None


def _expression_type(node: Ast, symbols: SymbolTable) -> ScalarType:
    expression_type = node.get("exprType")
    if expression_type == "constant":
        return ScalarType("number")
    if expression_type == "booleanConstant":
        if not isinstance(node.get("value"), bool):
            raise ValueError("booleanConstant/value must be Boolean")
        return ScalarType("boolean")
    if expression_type == "enumConstant":
        enum_type = str(node.get("enumType", ""))
        value = str(node.get("value", ""))
        if not enum_type or not value:
            raise ValueError("enumConstant requires enumType and value")
        if symbols:
            metadata = _enum_metadata(symbols, enum_type)
            if metadata is None:
                raise ValueError(f"unknown Enum type: {enum_type}")
            if value not in _enum_values(metadata):
                raise ValueError(f"{value} is not a member of Enum {enum_type}")
        return ScalarType("enum", enum_type)
    if expression_type == "parameter":
        return ScalarType("number", unit=node.get("unit"))
    if expression_type == "signal":
        name = str(node.get("name", ""))
        metadata = symbols.get(name)
        if metadata is None:
            if symbols:
                raise ValueError(f"unknown signal: {name}")
            declared = node.get("valueType")
            if declared == "boolean":
                return ScalarType("boolean")
            if declared == "enum":
                return ScalarType("enum", node.get("enumType"))
            return ScalarType("number")

        actual = _metadata_type({**metadata, "name": name})
        if actual.kind == "number" and actual.unit:
            prefix = "same as "
            if actual.unit.startswith(prefix):
                referenced_name = actual.unit[len(prefix) :].strip()
                referenced_metadata = symbols.get(referenced_name)
                if referenced_metadata is None:
                    raise ValueError(
                        f"signal {name} unit references unknown signal "
                        f"{referenced_name!r}"
                    )
                referenced_type = _metadata_type(
                    {**referenced_metadata, "name": referenced_name}
                )
                actual = ScalarType("number", unit=referenced_type.unit)
        declared = node.get("valueType")
        expected_declared = {
            "number": "number",
            "boolean": "boolean",
            "enum": "enum",
        }.get(declared)
        if declared and expected_declared != actual.kind:
            raise ValueError(
                f"signal {name} AST type {declared!r} conflicts with knowledge type "
                f"{metadata.get('type')!r}"
            )
        if actual.kind == "enum" and node.get("enumType") not in {None, actual.enum_type}:
            raise ValueError(
                f"signal {name} Enum type {node.get('enumType')!r} conflicts with "
                f"{actual.enum_type!r}"
            )
        return actual
    if expression_type == "binary":
        left = _expression_type(node["left"], symbols)
        right = _expression_type(node["right"], symbols)
        if left.kind != "number" or right.kind != "number":
            raise ValueError("arithmetic operands must be numeric")
        operator = node.get("operator")
        if operator in {"add", "subtract"}:
            if left.unit and right.unit and left.unit != right.unit:
                raise ValueError(
                    f"incompatible arithmetic units: {left.unit!r} and {right.unit!r}"
                )
            return ScalarType("number", unit=left.unit or right.unit)
        if operator not in {"multiply", "divide"}:
            raise ValueError(f"unknown arithmetic operator: {operator!r}")
        return ScalarType("number")
    raise ValueError(f"unknown expression type: {expression_type!r}")


def _validate_formula(node: Ast, symbols: SymbolTable) -> None:
    node_type = node.get("nodeType")
    if node_type == "predicate":
        left = _expression_type(node["left"], symbols)
        right = _expression_type(node["right"], symbols)
        relation = node.get("relation")
        if left.kind != right.kind:
            raise ValueError(
                f"predicate compares incompatible types: {left.kind} and {right.kind}"
            )
        if left.kind == "number":
            if relation not in NUMERIC_RELATIONS:
                raise ValueError(f"invalid numeric relation: {relation!r}")
            if left.unit and right.unit and left.unit != right.unit:
                raise ValueError(
                    f"predicate compares incompatible units: {left.unit!r} and "
                    f"{right.unit!r}"
                )
        else:
            if relation not in EQUALITY_RELATIONS:
                raise ValueError(
                    f"{left.kind} predicates only support == and !="
                )
            if left.kind == "enum" and left.enum_type != right.enum_type:
                raise ValueError(
                    f"predicate compares different Enum types: {left.enum_type!r} "
                    f"and {right.enum_type!r}"
                )
        return
    if node_type == "boolean":
        for operand in node.get("operands", []):
            _validate_formula(operand, symbols)
        return
    if node_type in {"temporal", "pastTemporal"}:
        interval = node.get("interval", {})
        lower = interval.get("lower")
        upper = interval.get("upper")
        if not isinstance(lower, (int, float)) or lower < 0:
            raise ValueError("time interval lower bound must be non-negative")
        if upper != "inf":
            if not isinstance(upper, (int, float)) or upper < lower:
                raise ValueError("time interval upper bound must be >= lower bound")
        for operand in node.get("operands", []):
            _validate_formula(operand, symbols)
        return
    if node_type == "edge":
        _validate_formula(node["operand"], symbols)
        return
    raise ValueError(f"unknown formula node type: {node_type!r}")


def validate_ast_semantics(
    ast: str | Mapping[str, Any],
    symbols: SymbolTable | None = None,
) -> None:
    """Raise ``ValueError`` when AST types, Enum values, units, or intervals conflict."""
    _validate_formula(_ast_object(ast), symbols or {})


def _compile_expression(node: Ast, symbols: SymbolTable) -> Ast:
    expression_type = node.get("exprType")
    if expression_type == "booleanConstant":
        return {"exprType": "constant", "value": 1 if node["value"] else 0}
    if expression_type == "enumConstant":
        metadata = _enum_metadata(symbols, node["enumType"])
        if metadata is None:
            raise ValueError(f"unknown Enum type: {node['enumType']}")
        values = _enum_values(metadata)
        try:
            code = values[node["value"]]
        except KeyError as exc:
            raise ValueError(
                f"{node['value']} is not a member of Enum {node['enumType']}"
            ) from exc
        return {"exprType": "constant", "value": code}
    if expression_type == "binary":
        node["left"] = _compile_expression(node["left"], symbols)
        node["right"] = _compile_expression(node["right"], symbols)
    return node


def _compile_formula(node: Ast, symbols: SymbolTable) -> Ast:
    node_type = node.get("nodeType")
    if node_type == "predicate":
        node["left"] = _compile_expression(node["left"], symbols)
        node["right"] = _compile_expression(node["right"], symbols)
    elif node_type in {"boolean", "temporal", "pastTemporal"}:
        node["operands"] = [
            _compile_formula(operand, symbols) for operand in node["operands"]
        ]
    elif node_type == "edge":
        node["operand"] = _compile_formula(node["operand"], symbols)
    return node


def compile_ast_for_rtamt(
    ast: str | Mapping[str, Any],
    symbols: SymbolTable,
) -> Ast:
    """Return a copy with Boolean and Enum constants encoded numerically."""
    data = _ast_object(ast)
    validate_ast_semantics(data, symbols)
    return _compile_formula(data, symbols)


def extract_ast_signals(ast: str | Mapping[str, Any]) -> set[str]:
    data = _ast_object(ast)
    names: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            if value.get("exprType") == "signal":
                names.add(str(value["name"]))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(data)
    return names


def validate_ast_with_rtamt(
    ast: str | Mapping[str, Any],
    symbols: SymbolTable,
) -> str:
    """Compile and parse an AST with RTAMT, returning the compiled STL string."""
    import rtamt

    compiled = compile_ast_for_rtamt(ast, symbols)
    stl = ast2stl(compiled)
    spec = rtamt.StlDiscreteTimeSpecification()
    for name in sorted(extract_ast_signals(compiled)):
        metadata = symbols[name]
        signal_type = str(metadata.get("type", "")).lower()
        rtamt_type = "int" if signal_type in {"bool", "enum", "int"} else "float"
        spec.declare_var(name, rtamt_type)
    spec.spec = stl
    spec.parse()
    return stl
