import re
from collections.abc import Mapping
from typing import Any

import rtamt

from STL2AST import stl2ast
from ast_semantics import validate_ast_with_rtamt

IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
IDENTIFIER_SCAN_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<name>{IDENTIFIER})(?![A-Za-z0-9_])"
)
RESERVED_WORDS = {
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
    "and",
    "or",
    "not",
    "implies",
    "iff",
    "true",
    "false",
}


def stl_syntax_validator(
    stl: str,
    symbols: Mapping[str, Mapping[str, Any]] | None = None,
) -> bool:
    if not isinstance(stl, str) or not stl.strip():
        return False

    try:
        if symbols is not None:
            ast = stl2ast(stl, symbols)
            validate_ast_with_rtamt(ast, symbols)
            return True

        spec = rtamt.StlDiscreteTimeSpecification()
        for variable in extract_variables(stl):
            spec.declare_var(variable, "float")
        spec.spec = stl
        spec.parse()
        return True
    except Exception:
        return False


def extract_variables(stl: str) -> set[str]:
    variables: set[str] = set()
    for match in IDENTIFIER_SCAN_RE.finditer(stl):
        name = match["name"]
        if name.lower() not in RESERVED_WORDS:
            variables.add(name)

    return variables
