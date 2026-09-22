"""Parse STL into source-aware nodes and compute deterministic semantic keys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from antlr4 import CommonTokenStream, InputStream, Token
from rtamt.antlr.parser.stl.StlLexer import StlLexer
from rtamt.antlr.parser.stl.StlParser import StlParser
from rtamt.antlr.parser.stl.error.parser_error_listener import STLParserErrorListener

from stl_metrics_utils import tokenize_formula


@dataclass(frozen=True)
class FormulaNode:
    kind: str
    children: tuple["FormulaNode", ...]
    interval: str | None
    start: int
    end: int
    raw: str

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class FormulaTree:
    text: str
    root: FormulaNode


_PARSER_TOKEN = {
    "AND": "and",
    "OR": "or",
    "NOT": "not",
    "IMPLIES": "->",
    "IFF": "<->",
    "!=": "!==",
}

_UNARY_KINDS = {
    "ExprNotContext": "not",
    "ExprAlwaysContext": "always",
    "ExprEvContext": "eventually",
    "ExprHistContext": "historically",
    "ExpreOnceContext": "once",
    "ExprRiseContext": "rise",
    "ExprFallContext": "fall",
    "ExprPreviousContext": "previous",
    "ExprNextContext": "next",
}

_BINARY_KINDS = {
    "ExprAndContext": "and",
    "ExprOrContext": "or",
    "ExprImpliesContext": "implies",
    "ExprIffContext": "iff",
    "ExprXorContext": "xor",
    "ExprUntilContext": "until",
    "ExprUnlessContext": "weak_until",
    "ExprSinceContext": "since",
}


def parse_formula(formula: str) -> FormulaTree:
    """Parse one complete formula while retaining normalized source spans."""
    tokens = tokenize_formula(formula)
    parser_text = " ".join(_PARSER_TOKEN.get(token, token) for token in tokens)
    listener = STLParserErrorListener()
    lexer = StlLexer(InputStream(parser_text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    stream = CommonTokenStream(lexer)
    parser = StlParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    context = parser.expression()
    if stream.LA(1) != Token.EOF:
        raise ValueError(f"完整公式之后存在多余内容：{stream.LT(1).text!r}")
    return FormulaTree(parser_text, _from_context(context, parser_text))


def _from_context(context, text: str) -> FormulaNode:
    context_name = type(context).__name__
    start = context.start.start
    end = context.stop.stop + 1
    raw = text[start:end]
    expression_children = tuple(
        _from_context(child, text)
        for child in context.children or ()
        if isinstance(child, StlParser.ExpressionContext)
    )

    if context_name == "ExprParenContext":
        return FormulaNode("group", expression_children, None, start, end, raw)

    if context_name in _UNARY_KINDS:
        interval = _interval_text(context)
        return FormulaNode(
            _UNARY_KINDS[context_name], expression_children, interval, start, end, raw
        )

    if context_name in _BINARY_KINDS:
        interval = _interval_text(context)
        return FormulaNode(
            _BINARY_KINDS[context_name], expression_children, interval, start, end, raw
        )

    if context_name == "ExprPredicateContext":
        comparison = context.comparisonOp().getText().replace("!==", "!=")
        return FormulaNode(
            f"cmp:{comparison}", expression_children, None, start, end, raw
        )

    # Arithmetic is not rewritten. Keeping the complete real expression as an
    # atomic term is sufficient for the comparisons present in this project.
    return FormulaNode("term", (), None, start, end, context.getText())


def _interval_text(context) -> str | None:
    interval_method = getattr(context, "interval", None)
    if interval_method is None:
        return None
    interval = interval_method()
    return interval.getText().replace(",", ":") if interval is not None else None


def iter_nodes(node: FormulaNode, path: tuple[int, ...] = ()) -> Iterable[tuple[tuple[int, ...], FormulaNode]]:
    yield path, node
    for index, child in enumerate(node.children):
        yield from iter_nodes(child, path + (index,))


# A semantic key is a disjunctive normal form over signed, hashable atoms.
# This preserves the min/max quantitative identities represented by the rule
# catalog without introducing classical true/false simplifications at zero.
Literal = tuple[str, tuple]
Clause = frozenset[Literal]
Dnf = frozenset[Clause]


def semantic_key(node: FormulaNode) -> tuple:
    return _freeze_dnf(_dnf(node, False))


def _dnf(node: FormulaNode, negated: bool) -> Dnf:
    kind = node.kind
    if kind == "group":
        return _dnf(node.children[0], negated)
    if kind == "not":
        return _dnf(node.children[0], not negated)

    if kind == "and":
        left = _dnf(node.children[0], negated)
        right = _dnf(node.children[1], negated)
        return _dnf_or(left, right) if negated else _dnf_and(left, right)
    if kind == "or":
        left = _dnf(node.children[0], negated)
        right = _dnf(node.children[1], negated)
        return _dnf_and(left, right) if negated else _dnf_or(left, right)
    if kind == "implies":
        if negated:
            return _dnf_and(_dnf(node.children[0], False), _dnf(node.children[1], True))
        return _dnf_or(_dnf(node.children[0], True), _dnf(node.children[1], False))

    if kind.startswith("cmp:"):
        return _comparison_dnf(kind[4:], node.children, negated)

    if kind in {"always", "eventually", "historically", "once"}:
        return _temporal_dnf(node, negated)

    if kind in {"rise", "fall"}:
        child = node.children[0]
        child_key = semantic_key(child) if kind == "rise" else _freeze_dnf(_dnf(child, True))
        return _literal_dnf(("edge", "rise", child_key), negated)

    if kind in {"until", "since"}:
        left_key = semantic_key(node.children[0])
        right_key = semantic_key(node.children[1])
        if node.interval is None and left_key == right_key:
            return _dnf(node.children[0], negated)
        atom = ("temporal_binary", kind, node.interval, left_key, right_key)
        return _literal_dnf(atom, negated)

    if kind == "term":
        return _literal_dnf(("term", node.raw), negated)

    atom = (
        "opaque",
        kind,
        node.interval,
        tuple(semantic_key(child) for child in node.children),
    )
    return _literal_dnf(atom, negated)


def _comparison_dnf(operator: str, children: tuple[FormulaNode, ...], negated: bool) -> Dnf:
    left, right = (child.raw for child in children)
    if operator == "<":
        atom, sign = ("lt", left, right), negated
    elif operator == ">":
        atom, sign = ("lt", right, left), negated
    elif operator == "<=":
        atom, sign = ("lt", right, left), not negated
    elif operator == ">=":
        atom, sign = ("lt", left, right), not negated
    elif operator == "==":
        atom, sign = ("eq", *sorted((left, right))), negated
    elif operator == "!=":
        atom, sign = ("eq", *sorted((left, right))), not negated
    else:
        atom, sign = ("comparison", operator, left, right), negated
    return _literal_dnf(atom, sign)


def _temporal_dnf(node: FormulaNode, negated: bool) -> Dnf:
    kind = node.kind
    child = node.children[0]
    if kind in {"eventually", "always"}:
        base = "eventually"
    else:
        base = "once"

    if kind in {"eventually", "once"}:
        child_dnf = _dnf(child, False)
        temporal_negated = negated
    else:
        child_dnf = _dnf(child, True)
        temporal_negated = not negated

    # E(E(P)) = E(P) and O(O(P)) = O(P) for unbounded operators.
    nested = _single_literal(child_dnf)
    if node.interval is None and nested is not None:
        nested_sign, nested_atom = nested
        if (
            nested_sign == "+"
            and nested_atom[:3] == ("temporal", base, None)
        ):
            return _literal_dnf(nested_atom, temporal_negated)

    pieces = []
    for clause in child_dnf:
        child_key = _freeze_dnf(frozenset({clause}))
        pieces.append(_literal_dnf(("temporal", base, node.interval, child_key), temporal_negated))

    if not pieces:
        raise ValueError("时序算子的子公式不能为空")
    combine = _dnf_and if temporal_negated else _dnf_or
    result = pieces[0]
    for piece in pieces[1:]:
        result = combine(result, piece)
    return result


def _literal_dnf(atom: tuple, negated: bool) -> Dnf:
    return frozenset({frozenset({("-" if negated else "+", atom)})})


def _single_literal(dnf: Dnf) -> Literal | None:
    if len(dnf) != 1:
        return None
    clause = next(iter(dnf))
    return next(iter(clause)) if len(clause) == 1 else None


def _dnf_or(left: Dnf, right: Dnf) -> Dnf:
    return _absorb(left | right)


def _dnf_and(left: Dnf, right: Dnf) -> Dnf:
    return _absorb(
        frozenset(left_clause | right_clause for left_clause in left for right_clause in right)
    )


def _absorb(dnf: Dnf) -> Dnf:
    # A or (A and B) = A. This also removes duplicate clauses/literals.
    return frozenset(
        clause for clause in dnf
        if not any(other < clause for other in dnf)
    )


def _freeze_dnf(dnf: Dnf) -> tuple:
    return tuple(
        sorted(
            (tuple(sorted(clause, key=repr)) for clause in dnf),
            key=repr,
        )
    )
