import json
import re
from collections.abc import Mapping
from typing import Any


TOKEN_RE = re.compile(
    r"<->|->|<=|>=|==|!=|&&|\|\||[()\[\]:,+*/<>-]|"
    r"=|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[A-Za-z_][A-Za-z0-9_./]*"
)

BOOL_OPS = {"and", "or", "not"}
FUTURE_OPS = {"always", "eventually", "until", "weak_until", "release"}
PAST_OPS = {"once", "historically", "since"}
UNARY_TEMPORAL = {"always", "eventually", "once", "historically"}
BINARY_TEMPORAL = {"until", "weak_until", "release", "since"}
EDGE_OPS = {"rise", "fall", "peak"}
RELATIONS = {"<", "<=", ">", ">=", "==", "!="}
ARITH_OPS = {"+": "add", "-": "subtract", "*": "multiply", "/": "divide"}


def stl2ast(stl, symbols=None):
    """Parse STL into AST JSON.

    ``symbols`` is an optional scenario-scoped mapping from signal name to
    metadata.  When supplied, Boolean literals and Enum members are preserved
    as typed constants instead of being mistaken for signal names.
    """
    return json.dumps(
        _Parser(_tokenize(stl), symbols or {}).parse(),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _tokenize(stl):
    text = str(stl)
    replacements = {
        "↔": "<->",
        "→": "->",
        "⇒": "->",
        "=>": "->",
        "∧": "and",
        "∨": "or",
        "¬": "not",
        "≤": "<=",
        "≥": ">=",
        "□": "always",
        "◇": "eventually",
    }
    for old, new in replacements.items():
        text = text.replace(old, f" {new} ")
    text = re.sub(r"&&|&", " and ", text)
    text = re.sub(r"\|\||\|", " or ", text)
    text = re.sub(r"!(?!=)", " not ", text)
    tokens = TOKEN_RE.findall(text)
    result = []
    for token in tokens:
        low = token.lower()
        if low in BOOL_OPS | FUTURE_OPS | PAST_OPS | EDGE_OPS:
            result.append(low)
        elif token in {"&&"}:
            result.append("and")
        elif token in {"||"}:
            result.append("or")
        elif token == "=":
            result.append("==")
        else:
            result.append(token)
    return result


def _interval(lower=0, upper="inf"):
    return {
        "lower": lower,
        "upper": upper,
        "lowerInclusive": True,
        "upperInclusive": upper != "inf",
    }


def _number(token):
    value = float(token)
    return int(value) if value.is_integer() else value


def _expr(token, symbols):
    if _is_number(token):
        return {"exprType": "constant", "value": _number(token)}
    if token.lower() in {"true", "false"}:
        return {"exprType": "booleanConstant", "value": token.lower() == "true"}

    node = {"exprType": "signal", "name": token}
    metadata = symbols.get(token)
    if not metadata:
        return node

    signal_type = str(metadata.get("type", "")).lower()
    if signal_type == "bool":
        node["valueType"] = "boolean"
    elif signal_type == "enum":
        node["valueType"] = "enum"
        node["enumType"] = metadata.get("enum_type", token)
    elif signal_type in {"float", "int", "number", "numeric"}:
        node["valueType"] = "number"
    return node


def _is_number(token):
    try:
        float(token)
        return True
    except ValueError:
        return False


class _Parser:
    def __init__(self, tokens, symbols: Mapping[str, Mapping[str, Any]]):
        self.tokens = tokens
        self.symbols = symbols
        self.i = 0

    def parse(self):
        node = self._iff()
        if self._peek() is not None:
            raise ValueError(f"unexpected token: {self._peek()}")
        return node

    def _iff(self):
        node = self._implies()
        while self._accept("<->"):
            node = self._boolean("iff", [node, self._implies()])
        return node

    def _implies(self):
        node = self._or()
        if self._accept("->"):
            node = self._boolean("implies", [node, self._implies()])
        return node

    def _or(self):
        nodes = [self._and()]
        while self._accept("or"):
            nodes.append(self._and())
        return nodes[0] if len(nodes) == 1 else self._boolean("or", nodes)

    def _and(self):
        nodes = [self._temporal_binary()]
        while self._accept("and"):
            nodes.append(self._temporal_binary())
        return nodes[0] if len(nodes) == 1 else self._boolean("and", nodes)

    def _temporal_binary(self):
        node = self._unary()
        while self._peek() in BINARY_TEMPORAL:
            op = self._next()
            interval = self._optional_interval()
            right = self._unary()
            node = self._temporal(op, interval, [node, right])
        return node

    def _unary(self):
        token = self._peek()
        if token == "not":
            self._next()
            return self._boolean("not", [self._unary()])
        if token in UNARY_TEMPORAL:
            op = self._next()
            return self._temporal(op, self._optional_interval(), [self._unary()])
        if token in EDGE_OPS:
            op = self._next()
            return {"nodeType": "edge", "operator": op, "operand": self._unary()}
        return self._primary()

    def _primary(self):
        if self._accept("("):
            node = self._iff()
            self._expect(")")
            return node
        return self._predicate()

    def _predicate(self):
        left = self._real_expr()
        relation = self._next()
        if relation not in RELATIONS:
            raise ValueError(f"expected relation, got: {relation}")
        right = self._real_expr()
        left, right = self._coerce_enum_constants(left, right)
        return {
            "nodeType": "predicate",
            "left": left,
            "relation": relation,
            "right": right,
        }

    def _real_expr(self):
        node = self._real_term()
        while self._peek() in {"+", "-"}:
            node = self._binary_expr(ARITH_OPS[self._next()], node, self._real_term())
        return node

    def _real_term(self):
        node = self._real_factor()
        while self._peek() in {"*", "/"}:
            node = self._binary_expr(ARITH_OPS[self._next()], node, self._real_factor())
        return node

    def _real_factor(self):
        if self._accept("-"):
            operand = self._real_factor()
            if operand.get("exprType") == "constant":
                return {"exprType": "constant", "value": -operand["value"]}
            return {
                "exprType": "binary",
                "operator": "subtract",
                "left": {"exprType": "constant", "value": 0},
                "right": operand,
            }
        if self._accept("("):
            node = self._real_expr()
            self._expect(")")
            return node
        return _expr(self._next(), self.symbols)

    def _coerce_enum_constants(self, left, right):
        left_type = self._enum_type(left)
        right_type = self._enum_type(right)
        if left_type and not right_type:
            right = self._enum_member(right, left_type)
        elif right_type and not left_type:
            left = self._enum_member(left, right_type)
        return left, right

    def _enum_type(self, node):
        if node.get("exprType") == "enumConstant":
            return node["enumType"]
        if node.get("exprType") != "signal" or node.get("valueType") != "enum":
            return None
        return node["enumType"]

    def _enum_member(self, node, enum_type):
        if node.get("exprType") != "signal":
            return node
        token = node["name"]
        if token in self.symbols:
            return node

        for metadata in self.symbols.values():
            if str(metadata.get("type", "")).lower() != "enum":
                continue
            if metadata.get("enum_type") != enum_type:
                continue
            values = metadata.get("enum_values", {})
            if token in values:
                return {
                    "exprType": "enumConstant",
                    "enumType": enum_type,
                    "value": token,
                }
        return node

    def _binary_expr(self, op, left, right):
        return {"exprType": "binary", "operator": op, "left": left, "right": right}

    def _optional_interval(self):
        if not self._accept("["):
            return _interval()
        lower = self._bound(self._next())
        if self._peek() not in {":", ","}:
            raise ValueError(f"expected interval separator, got: {self._peek()}")
        self._next()
        upper = self._bound(self._next())
        self._expect("]")
        return _interval(lower, upper)

    def _bound(self, token):
        return "inf" if token in {"inf", "∞"} else _number(token)

    def _temporal(self, op, interval, operands):
        kind = "pastTemporal" if op in PAST_OPS else "temporal"
        return {"nodeType": kind, "operator": op, "interval": interval, "operands": operands}

    def _boolean(self, op, operands):
        return {"nodeType": "boolean", "operator": op, "operands": operands}

    def _peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _next(self):
        token = self._peek()
        if token is None:
            raise ValueError("unexpected end of formula")
        self.i += 1
        return token

    def _accept(self, token):
        if self._peek() == token:
            self.i += 1
            return True
        return False

    def _expect(self, token):
        actual = self._next()
        if actual != token:
            raise ValueError(f"expected {token}, got: {actual}")
