import re

import rtamt


IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
IDENTIFIER_SCAN_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<name>{IDENTIFIER})(?![A-Za-z0-9_])"
)
INVALID_CHARACTER_RE = re.compile(r"[^A-Za-z0-9_\s.,()\[\]+*/<>=!&|:\-]")
BOOL_LITERAL_RE = re.compile(r"\b(?:true|false)\b", re.IGNORECASE)
BOOL_COMPARISON_RE = re.compile(
    rf"(?:\b(?P<left>{IDENTIFIER})\b\s*(?:==|!=|!==)\s*"
    rf"(?P<right_literal>true|false)\b|"
    rf"\b(?P<left_literal>true|false)\b\s*(?:==|!=|!==)\s*"
    rf"\b(?P<right>{IDENTIFIER})\b)",
    re.IGNORECASE,
)
NUMERIC_COMPARISON_RE = re.compile(
    rf"(?:\b(?P<left>{IDENTIFIER})\b\s*(?:<=|>=|==|!=|!==|<|>)\s*"
    rf"(?P<right>{IDENTIFIER}|[-+]?(?:\d+(?:\.\d*)?|\.\d+))|"
    rf"(?P<left_number>[-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*"
    rf"(?:<=|>=|==|!=|!==|<|>)\s*\b(?P<right_identifier>{IDENTIFIER})\b)"
)
ARITHMETIC_IDENTIFIER_RE = re.compile(
    rf"(?:\b(?P<left>{IDENTIFIER})\b\s*[+*/-]|"
    rf"[+*/-]\s*\b(?P<right>{IDENTIFIER})\b)"
)
NUMERIC_FUNCTION_RE = re.compile(
    r"\b(?:abs|sqrt|exp|pow)\s*\((?P<args>[^()]*)\)", re.IGNORECASE
)

RESERVED_WORDS = {
    "always",
    "eventually",
    "until",
    "unless",
    "weak_until",
    "release",
    "once",
    "historically",
    "since",
    "next",
    "prev",
    "previous",
    "rise",
    "fall",
    "peak",
    "abs",
    "sqrt",
    "exp",
    "pow",
    "and",
    "or",
    "xor",
    "not",
    "implies",
    "iff",
    "true",
    "false",
}
SYMBOLIC_RESERVED_WORDS = {"G", "F", "U", "W", "H", "O", "S", "X", "Y"}


def stl_syntax_validator(stl: str) -> bool:
    if not isinstance(stl, str) or not stl.strip():
        return False
    if any(ord(char) > 127 for char in stl):
        return False
    if INVALID_CHARACTER_RE.search(stl):
        return False

    try:
        variable_types = infer_variable_types(stl)
        parse_formula = normalize_boolean_literals(stl)

        spec = rtamt.StlDiscreteTimeSpecification()
        for variable, variable_type in variable_types.items():
            spec.declare_var(variable, variable_type)
        spec.spec = parse_formula
        spec.parse()
        return True
    except Exception:
        return False


def extract_variables(stl: str) -> set[str]:
    variables: set[str] = set()
    for match in IDENTIFIER_SCAN_RE.finditer(stl):
        name = match["name"]
        if name in SYMBOLIC_RESERVED_WORDS:
            continue
        if name.lower() not in RESERVED_WORDS:
            variables.add(name)
    return variables


def infer_variable_types(stl: str) -> dict[str, str]:
    variables = extract_variables(stl)
    explicit_boolean: set[str] = set()
    numeric: set[str] = set()

    for match in BOOL_COMPARISON_RE.finditer(stl):
        name = match["left"] or match["right"]
        if name and name in variables:
            explicit_boolean.add(name)

    for match in NUMERIC_COMPARISON_RE.finditer(stl):
        if BOOL_LITERAL_RE.search(match.group(0)):
            continue
        names = (match["left"], match["right"], match["right_identifier"])
        for name in names:
            if name and name in variables and not BOOL_LITERAL_RE.fullmatch(name):
                numeric.add(name)

    for match in ARITHMETIC_IDENTIFIER_RE.finditer(stl):
        for name in (match["left"], match["right"]):
            if name and name in variables:
                numeric.add(name)

    for match in NUMERIC_FUNCTION_RE.finditer(stl):
        numeric.update(extract_variables(match["args"]))

    conflicts = explicit_boolean & numeric
    if conflicts:
        names = ", ".join(sorted(conflicts))
        raise ValueError(f"variables used as both boolean and numeric: {names}")

    return {
        variable: "int" if variable in explicit_boolean or variable not in numeric else "float"
        for variable in sorted(variables)
    }


def normalize_boolean_literals(stl: str) -> str:
    return BOOL_LITERAL_RE.sub(
        lambda match: "1" if match.group(0).lower() == "true" else "0",
        stl,
    )
