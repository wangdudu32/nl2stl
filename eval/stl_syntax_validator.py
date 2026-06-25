import re

import rtamt

IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
COMPARISON_OPERATOR = r"""
    <= | >= | == | !=
    | (?<![-<>=]) < (?![-=>])
    | (?<![-<>=]) > (?!=)
    | (?<![<>=]) = (?![=>])
"""
COMPARISON_RE = re.compile(
    rf"""
    \b(?P<left>{IDENTIFIER})
    \s*
    (?:{COMPARISON_OPERATOR})
    \s*
    (?P<right>[^()]+?)
    (?=\s+(?:and|or)\b|\)|->|$)
    """,
    re.VERBOSE,
)
IDENTIFIER_RE = re.compile(rf"^{IDENTIFIER}$")


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
    for match in COMPARISON_RE.finditer(stl):
        variables.add(match["left"])

        right = match["right"].strip()
        if IDENTIFIER_RE.fullmatch(right):
            variables.add(right)

    return variables
