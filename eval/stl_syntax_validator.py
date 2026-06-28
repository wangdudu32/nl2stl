import re

import rtamt

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


def stl_syntax_validator(stl: str) -> bool:
    if not isinstance(stl, str) or not stl.strip():
        return False

    try:
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
