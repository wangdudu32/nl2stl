import json


def ast2stl(ast: str) -> str:
    data = json.loads(ast)
    bool_prec = {"iff": 10, "implies": 20, "or": 40, "and": 50, "not": 60}
    arith = {
        "add": (" + ", 10),
        "subtract": (" - ", 10),
        "multiply": (" * ", 20),
        "divide": (" / ", 20),
    }
    bin_temp_prec, unary_prec, atom_prec = 30, 70, 90

    def interval(value):
        if value is None:
            return None
        lower, upper = value.get("lower", 0), value.get("upper", "inf")
        if lower == 0 and upper == "inf":
            return None
        left = "[" if value.get("lowerInclusive", True) else "("
        right = "]" if upper != "inf" and value.get("upperInclusive", True) else ")"
        return f"{left}{lower}:{upper}{right}"

    def expr(node):
        kind = node["exprType"]
        if kind in {"signal", "parameter"}:
            return node["name"], 100
        if kind == "constant":
            return str(node["value"]), 100
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
            return f"{left} {node['relation']} {right}", atom_prec
        if kind == "boolean":
            op, operands = node["operator"], node["operands"]
            prec = bool_prec[op]
            if op == "not":
                text, child = formula(operands[0])
                return f"not {f'({text})' if child < prec else text}", prec
            parts = []
            for operand in operands:
                text, child = formula(operand)
                if child < prec or (child == prec and op in {"implies", "iff"}):
                    text = f"({text})"
                parts.append(text)
            return {"and": " and ", "or": " or ", "implies": " -> ", "iff": " <-> "}[op].join(parts), prec
        if kind in {"temporal", "pastTemporal"}:
            op, operands = node["operator"], node["operands"]
            rng = interval(node.get("interval"))
            if op in {"always", "eventually", "historically", "once"}:
                text, _ = formula(operands[0])
                return f"{op if rng is None else op + rng} ({text})", unary_prec
            mid = op if rng is None else op + rng
            left, lp = formula(operands[0])
            right, rp = formula(operands[1])
            return (
                f"{f'({left})' if lp <= bin_temp_prec else left} {mid} "
                f"{f'({right})' if rp <= bin_temp_prec else right}",
                bin_temp_prec,
            )
        if kind == "edge":
            text, _ = formula(node["operand"])
            mode = node.get("mode", "strict")
            op = node["operator"] if mode == "strict" else f"{node['operator']}[{mode}]"
            return f"{op}({text})", unary_prec
        if kind == "statistical":
            text, _ = formula(node["operand"])
            threshold = node["threshold"]
            rng = interval(node.get("interval")) or "[0:inf)"
            return f"{node['operator']}{{{rng}}}({text}) {threshold['relation']} {threshold['value']}", unary_prec
        raise ValueError(f"Unknown nodeType: {kind}")

    return formula(data)[0]
