"""复用 DSL → STL 转换器，验证 DSL 的语法和结构约束。

用法：
    from dsl_validator import validate_dsl
    valid, error = validate_dsl("sig1 is greater than 5")
    # (True, None)

只接受 DSL 正文；不检查其含义是否与原始自然语言一致。
"""

from dsl_to_stl import convert_dsl_to_stl

__all__ = ["validate_dsl"]


def validate_dsl(dsl_text: str) -> tuple[bool, str | None]:
    """合法时返回 (True, None)，否则返回 (False, 第一处错误信息)。

    语法和时间区间规则与转换器一致，错误信息保留行号、列号。
    输入不是字符串时抛出 TypeError，与转换接口保持一致。
    """
    try:
        convert_dsl_to_stl(dsl_text)
    except ValueError as error:
        return False, str(error)
    return True, None
