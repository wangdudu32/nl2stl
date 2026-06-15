from __future__ import annotations

from typing import Any


class STLJSONToStringConverter:
    """按运算符优先级将 AST 确定性转换为紧凑 STL 文本。"""

    _BOOLEAN_PRECEDENCE = {
        "iff": 10,
        "implies": 20,
        "or": 40,
        "and": 50,
        "not": 60,
    }
    _BINARY_TEMPORAL_PRECEDENCE = 30
    _UNARY_PRECEDENCE = 70
    _ATOM_PRECEDENCE = 90
    _ARITHMETIC = {
        "add": (" + ", 10),
        "subtract": (" - ", 10),
        "multiply": (" * ", 20),
        "divide": (" / ", 20),
    }

    def convert(self, data: dict[str, Any]) -> str:
        """输出不改变 AST 语义且没有冗余外层括号的 STL。"""

        return self._render_formula(data)[0]

    def _render_formula(self, node: dict[str, Any]) -> tuple[str, int]:
        handlers = {
            "predicate": self._render_predicate,
            "boolean": self._render_boolean,
            "temporal": self._render_temporal,
            "pastTemporal": self._render_past_temporal,
            "edge": self._render_edge,
            "statistical": self._render_statistical,
        }
        node_type = node.get("nodeType")
        if node_type not in handlers:
            raise ValueError(f"Unknown nodeType: {node_type}")
        return handlers[node_type](node)

    def _render_expression(self, expr: dict[str, Any]) -> tuple[str, int]:
        expression_type = expr["exprType"]
        if expression_type == "signal":
            return expr["name"], 100
        if expression_type == "constant":
            return str(expr["value"]), 100
        if expression_type == "parameter":
            return expr["name"], 100
        if expression_type != "binary":
            raise ValueError(f"Unknown exprType: {expression_type}")

        operator = expr["operator"]
        symbol, precedence = self._ARITHMETIC[operator]
        left_text, left_precedence = self._render_expression(expr["left"])
        right_text, right_precedence = self._render_expression(expr["right"])
        if left_precedence < precedence:
            left_text = f"({left_text})"
        # 右侧同级的减法和除法必须分组，避免改变 AST 结合关系。
        if right_precedence < precedence or (
            right_precedence == precedence and operator in {"subtract", "divide"}
        ):
            right_text = f"({right_text})"
        return f"{left_text}{symbol}{right_text}", precedence

    def _render_predicate(self, node: dict[str, Any]) -> tuple[str, int]:
        left, _ = self._render_expression(node["left"])
        right, _ = self._render_expression(node["right"])
        return f"{left} {node['relation']} {right}", self._ATOM_PRECEDENCE

    def _render_boolean(self, node: dict[str, Any]) -> tuple[str, int]:
        operator = node["operator"]
        precedence = self._BOOLEAN_PRECEDENCE[operator]
        operands = node["operands"]
        if operator == "not":
            inner, inner_precedence = self._render_formula(operands[0])
            if inner_precedence < precedence:
                inner = f"({inner})"
            return f"not {inner}", precedence

        symbols = {"and": " and ", "or": " or ", "implies": " -> ", "iff": " <-> "}
        rendered: list[str] = []
        for operand in operands:
            text, child_precedence = self._render_formula(operand)
            if child_precedence < precedence or (
                child_precedence == precedence and operator in {"implies", "iff"}
            ):
                text = f"({text})"
            rendered.append(text)
        return symbols[operator].join(rendered), precedence

    def _render_temporal(self, node: dict[str, Any]) -> tuple[str, int]:
        operator = node["operator"]
        interval = self._render_interval(node.get("interval"))
        operands = node["operands"]
        if operator in {"always", "eventually"}:
            prefix = operator if interval is None else f"{operator}{interval}"
            inner, _ = self._render_formula(operands[0])
            return f"{prefix} ({inner})", self._UNARY_PRECEDENCE
        if operator in {"until", "weak_until", "release"}:
            middle = operator if interval is None else f"{operator}{interval}"
            return self._render_binary_temporal(operands, middle)
        raise ValueError(f"Unknown temporal operator: {operator}")

    def _render_past_temporal(self, node: dict[str, Any]) -> tuple[str, int]:
        operator = node["operator"]
        interval = self._render_interval(node.get("interval"))
        operands = node["operands"]
        if operator in {"historically", "once"}:
            prefix = operator if interval is None else f"{operator}{interval}"
            inner, _ = self._render_formula(operands[0])
            return f"{prefix} ({inner})", self._UNARY_PRECEDENCE
        if operator == "since":
            middle = "since" if interval is None else f"since{interval}"
            return self._render_binary_temporal(operands, middle)
        raise ValueError(f"Unknown past temporal operator: {operator}")

    def _render_binary_temporal(
        self, operands: list[dict[str, Any]], operator: str
    ) -> tuple[str, int]:
        rendered: list[str] = []
        for operand in operands:
            text, precedence = self._render_formula(operand)
            if precedence <= self._BINARY_TEMPORAL_PRECEDENCE:
                text = f"({text})"
            rendered.append(text)
        return (
            f"{rendered[0]} {operator} {rendered[1]}",
            self._BINARY_TEMPORAL_PRECEDENCE,
        )

    def _render_edge(self, node: dict[str, Any]) -> tuple[str, int]:
        operand, _ = self._render_formula(node["operand"])
        mode = node.get("mode", "strict")
        prefix = node["operator"] if mode == "strict" else f"{node['operator']}[{mode}]"
        return f"{prefix}({operand})", self._UNARY_PRECEDENCE

    def _render_statistical(self, node: dict[str, Any]) -> tuple[str, int]:
        interval = self._render_interval(node.get("interval")) or "[0:inf)"
        operand, _ = self._render_formula(node["operand"])
        threshold = node["threshold"]
        return (
            f"{node['operator']}{{{interval}}}({operand}) "
            f"{threshold['relation']} {threshold['value']}",
            self._UNARY_PRECEDENCE,
        )

    @staticmethod
    def _render_interval(interval: dict[str, Any] | None) -> str | None:
        if interval is None:
            return None
        lower = interval.get("lower", 0)
        upper = interval.get("upper", "inf")
        if lower == 0 and upper == "inf":
            return None
        left = "[" if interval.get("lowerInclusive", True) else "("
        right = "]" if upper != "inf" and interval.get("upperInclusive", True) else ")"
        return f"{left}{lower}:{upper}{right}"
