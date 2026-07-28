import json
from collections.abc import Mapping
from typing import Any


def ast2stl(ast: str | Mapping[str, Any]) -> str:
    data = json.loads(ast) if isinstance(ast, str) else dict(ast)
    bool_prec = {"iff": 10, "implies": 20, "or": 40, "and": 50, "not": 60}
    arith = {
        "add": (" + ", 10),
        "subtract": (" - ", 10),
        "multiply": (" * ", 20),
        "divide": (" / ", 20),
    }
    bin_temp_prec, unary_prec, atom_prec = 55, 70, 90

    def interval(value):
        if value is None:
            return None
        lower, upper = value.get("lower", 0), value.get("upper", "inf")
        if lower == 0 and upper == "inf":
            return None
        left = "[" if value.get("lowerInclusive", True) else "("
        right = "]" if upper != "inf" and value.get("upperInclusive", True) else ")"
        return f"{left}{lower}:{upper}{right}"

    def with_interval(op, rng):
        return op if rng is None else f"{op} {rng}"

    def wrap(text):
        return f"({text})"

    def node_info(node, text, prec):
        return {
            "text": text,
            "prec": prec,
            "nodeType": node.get("nodeType"),
            "operator": node.get("operator"),
        }

    def expr(node):
        kind = node["exprType"]
        if kind in {"signal", "parameter"}:
            return node["name"], 100
        if kind == "constant":
            return str(node["value"]), 100
        if kind == "booleanConstant":
            return ("true" if node["value"] else "false"), 100
        if kind == "enumConstant":
            return node["value"], 100
        op = node["operator"]
        symbol, prec = arith[op]
        left, lp = expr(node["left"])
        right, rp = expr(node["right"])
        if lp < prec:
            left = f"({left})"
        if rp < prec or (rp == prec and op in {"subtract", "divide"}):
            right = f"({right})"
        return f"{left}{symbol}{right}", prec

    def formula(node):
        kind = node["nodeType"]
        if kind == "predicate":
            left, _ = expr(node["left"])
            right, _ = expr(node["right"])
            return node_info(node, f"{left} {node['relation']} {right}", atom_prec)
        if kind == "boolean":
            op, operands = node["operator"], node["operands"]
            prec = bool_prec[op]
            if op == "not":
                child = formula(operands[0])
                if child["nodeType"] == "edge":
                    text = child["text"]
                else:
                    text = wrap(child["text"])
                return node_info(node, f"not {text}", prec)
            parts = []
            for operand in operands:
                child = formula(operand)
                text = child["text"]
                child_prec = child["prec"]
                child_op = child["operator"]
                if (
                    child_prec < prec
                    or (child_prec == prec and op in {"implies", "iff"})
                    or (child_prec == prec and child_op == op and op in {"and", "or"})
                    or (op == "or" and child_op == "and")
                ):
                    text = wrap(text)
                parts.append(text)
            return node_info(
                node,
                {"and": " and ", "or": " or ", "implies": " -> ", "iff": " <-> "}[op].join(parts),
                prec,
            )
        if kind in {"temporal", "pastTemporal"}:
            op, operands = node["operator"], node["operands"]
            rng = interval(node.get("interval"))
            if op in {"always", "eventually", "historically", "once"}:
                child = formula(operands[0])
                text = child["text"]
                if child["operator"] in {"implies", "iff"}:
                    text = f" {text} "
                return node_info(
                    node,
                    f"{with_interval(op, rng)} ({text})",
                    unary_prec,
                )
            mid = with_interval(op, rng)
            left = formula(operands[0])
            right = formula(operands[1])
            return node_info(
                node,
                f"{wrap(left['text'])} {mid} {wrap(right['text'])}",
                bin_temp_prec,
            )
        if kind == "edge":
            child = formula(node["operand"])
            mode = node.get("mode", "strict")
            op = node["operator"] if mode == "strict" else f"{node['operator']}[{mode}]"
            return node_info(node, f"{op} ({child['text']})", unary_prec)
        if kind == "statistical":
            child = formula(node["operand"])
            threshold = node["threshold"]
            rng = interval(node.get("interval")) or "[0:inf)"
            return node_info(
                node,
                f"{node['operator']}{{{rng}}}({child['text']}) {threshold['relation']} {threshold['value']}",
                unary_prec,
            )
        raise ValueError(f"Unknown nodeType: {kind}")

    return formula(data)["text"]
