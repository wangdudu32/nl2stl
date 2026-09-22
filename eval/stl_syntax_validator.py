"""直接使用 RTAMT 校验 STL，供六项指标共用。"""

import re
from decimal import Decimal

import rtamt
from antlr4 import CommonTokenStream, InputStream, Token
from rtamt.exception.exception import RTAMTException

from stl_metrics_utils import NUMBER_RE, RESERVED_TOKENS, tokenize_formula


def stl_syntax_validator(stl: str) -> bool:
    """合法时返回 True，非法时返回 False。"""
    return syntax_error(stl) is None


def syntax_error(stl: str) -> str | None:
    """返回第一处语法错误，合法时返回 None。"""
    if not isinstance(stl, str) or not stl.strip():
        return "STL 为空或不是字符串"
    if stl.strip() == "nlll":
        return "预测生成失败：nlll"
    try:
        build_spec(stl)
    except (ValueError, RTAMTException) as error:
        return str(error)
    return None


def validate_record(record: dict[str, str]) -> str | None:
    """标准答案非法时抛出异常；预测非法时返回原因，供指标计零。"""
    error = syntax_error(record["gold_stl"])
    if error is not None:
        raise ValueError(f"taskid={record['taskid']} 的 gold_stl 非法：{error}")
    return syntax_error(record["pred_stl"])


def extract_variables(stl: str) -> set[str]:
    """从 token 中提取变量，避免把科学计数法中的 e 当作变量。"""
    variables: set[str] = set()
    for token in tokenize_formula(stl):
        if token not in RESERVED_TOKENS and re.fullmatch(r"[^\W\d]\w*(?:\.[^\W\d]\w*)*", token):
            variables.add(token)
    return variables


def build_spec(stl: str, variables: list[str] | None = None):
    """统一算子和数字写法后构造 RTAMT 规格，保持括号和操作数顺序。"""
    tokens = tokenize_formula(stl)
    operators = {"AND": "and", "OR": "or", "NOT": "not", "IMPLIES": "->", "IFF": "<->", "!=": "!=="}
    formula = " ".join(operators.get(token, token) for token in tokens)
    for start, end in re.findall(rf"\[\s*({NUMBER_RE})\s*:\s*({NUMBER_RE})\s*\]", formula):
        if not Decimal(0) <= Decimal(start) <= Decimal(end):
            raise ValueError("时间区间必须满足 0 <= a <= b")
    spec = rtamt.StlDiscreteTimeSpecification()
    if variables is None:
        variables = sorted(extract_variables(stl))
    for variable in variables:
        spec.declare_var(variable, "float")
    # RTAMT 可把尾部内容当作另一条断言，这里要求恰好一个完整表达式。
    listener = spec.ast.parserErrorListenerType()
    lexer = spec.ast.antrlLexerType(InputStream(formula))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    stream = CommonTokenStream(lexer)
    parser = spec.ast.antrlParserType(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    parser.expression()
    if stream.LA(1) != Token.EOF:
        raise ValueError(f"完整公式之后存在多余内容：{stream.LT(1).text!r}")
    spec.spec = formula
    spec.parse()
    return spec
