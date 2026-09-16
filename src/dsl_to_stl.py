"""按 dsl_step1.md / dsl_step2.md 将 DSL 确定性地转换为 STL。

用法：
    from dsl_to_stl import convert_dsl_to_stl
    stl = convert_dsl_to_stl("sig1 is greater than 5")
    # (sig1 > 5)

只接受 DSL 正文，不接受 Markdown 代码围栏或自然语言说明。
关键字区分大小写；空白、缩进和换行不影响解析。
信号名支持 Unicode 字母或下划线开头的标识符及点分名称（如 ego.speed）。
数值支持带正负号的整数、小数；信号名和数值保留原文。
输出保留括号，可能比文档示例多一些冗余括号。
"""

import re
from decimal import Decimal

__all__ = ["convert_dsl_to_stl"]

_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
_SIGNAL = re.compile(r"[^\W\d]\w*(?:\.[^\W\d]\w*)*")
_COMPARISONS = {
    "is equal to": "==",
    "is not equal to": "!=",
    "is less than or equal to": "<=",
    "is less than": "<",
    "is greater than or equal to": ">=",
    "is greater than": ">",
}
_UNARY = {
    "it is not the case that": "not",
    "becomes true": "rise",
    "becomes false": "fall",
}


def convert_dsl_to_stl(dsl_text: str) -> str:
    """转换一个完整 DSL 表达式，返回 STL 字符串。

    Raises:
        TypeError: 输入不是字符串。
        ValueError: DSL 语法错误或时间区间不满足 0 <= a <= b。
            错误消息包含行号、列号。
    """
    if not isinstance(dsl_text, str):
        raise TypeError("dsl_text 必须是字符串")
    parser = _Parser(dsl_text)
    result = parser.expression()
    if parser.pos != len(parser.tokens):
        parser.error("完整表达式之后存在多余内容")
    return result


class _Parser:
    def __init__(self, text: str):
        self.text = text
        # 非分隔符片段保持完整，避免把 5abc 或 1.2.3 拆成合法数值。
        self.tokens = list(re.finditer(r"[{};\[\],]|[^\s{};\[\],]+", text))
        self.pos = 0

    def peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.tokens[index].group() if index < len(self.tokens) else ""

    def error(self, message: str):
        index = self.tokens[self.pos].start() if self.pos < len(self.tokens) else len(self.text)
        line = self.text.count("\n", 0, index) + 1
        column = index - self.text.rfind("\n", 0, index)
        found = repr(self.peek()) if self.peek() else "输入末尾"
        raise ValueError(f"第 {line} 行，第 {column} 列：{message}；实际为 {found}")

    def accept(self, phrase: str) -> bool:
        words = phrase.split()
        if all(self.peek(i) == word for i, word in enumerate(words)):
            self.pos += len(words)
            return True
        return False

    def expect(self, phrase: str):
        if not self.accept(phrase):
            self.error(f"需要 {phrase!r}")

    def value(self, *, time: bool = False) -> str:
        value = self.peek()
        if not _NUMBER.fullmatch(value) and (time or not _SIGNAL.fullmatch(value)):
            self.error("需要时间数值" if time else "需要信号名或数值")
        self.pos += 1
        return value

    def block(self) -> str:
        self.expect("{")
        result = self.expression()
        self.expect("}")
        return result

    @staticmethod
    def call(operator: str, body: str) -> str:
        # 解析结果以 '(' 开头时，最外层括号必定包围完整表达式。
        return operator + (body if body.startswith("(") else f"({body})")

    def window(self) -> tuple[str, str]:
        """返回 (future/past, 空字符串或 [a:b])。"""
        self.expect("the")
        if self.accept("entire"):
            if self.accept("future"):
                return "future", ""
            self.expect("past")
            return "past", ""

        if self.accept("next"):
            direction = "future"
        elif self.accept("previous"):
            direction = "past"
        else:
            self.error("需要 next、previous 或 entire")

        self.expect("[")
        start = self.value(time=True)
        self.expect(",")
        end = self.value(time=True)
        if not Decimal(0) <= Decimal(start) <= Decimal(end):
            self.error("时间区间必须满足 0 <= a <= b")
        self.expect("]")
        self.expect("time units")
        return direction, f"[{start}:{end}]"

    def expression(self) -> str:
        for phrase, operator in _UNARY.items():
            if self.accept(phrase):
                return self.call(operator, self.block())

        # 先识别比较，使 if、keep 等单词也可作为原样保留的信号名。
        if self.peek(1) == "is":
            return self.comparison()

        for phrase, operator in (("all of", "and"), ("any of", "or")):
            if self.accept(phrase):
                self.expect("{")
                items = []
                while self.peek() != "}":
                    items.append(self.expression())
                    self.expect(";")
                if len(items) < 2:
                    self.error(f"{phrase} 至少需要两个子表达式")
                self.expect("}")
                return "(" + f" {operator} ".join(items) + ")"

        if self.accept("if"):
            left = self.block()
            self.expect("then")
            right = self.block()
            return f"({left} -> {right})"

        for phrase, future, past in (
            ("throughout", "always", "historically"),
            ("at least once in", "eventually", "once"),
        ):
            if self.accept(phrase):
                direction, interval = self.window()
                operator = future if direction == "future" else past
                return self.call(operator + interval, self.block())

        if self.accept("keep"):
            left = self.block()
            if self.accept("until"):
                operator, required_direction = "until", "future"
            else:
                self.expect("since")
                operator, required_direction = "since", "past"
            direction, interval = self.window()
            if direction != required_direction:
                self.error(f"{operator} 必须使用 {required_direction} 时间窗口")
            right = self.block()
            return f"({left} {operator}{interval} {right})"

        return self.comparison()

    def comparison(self) -> str:
        left = self.value()
        for phrase, operator in _COMPARISONS.items():
            if self.accept(phrase):
                right = self.value()
                if operator == "!=":
                    return f"not({left} == {right})"
                return f"({left} {operator} {right})"
        self.error("需要规范中定义的比较句式，例如 'is equal to'")
