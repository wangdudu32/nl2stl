from __future__ import annotations

from dataclasses import dataclass

from .schemas import (
    Clarification,
    NumericExpression,
    PredicateExpression,
    SemanticPlan,
    SemanticRequirement,
    STLResult,
    TranslationFragment,
)


class SemanticValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Unit:
    dimensions: tuple[int, int]
    scale_to_si: float = 1.0
    name: str = "dimensionless"


UNITS = {
    "dimensionless": Unit((0, 0), 1.0, "dimensionless"),
    "boolean": Unit((0, 0), 1.0, "boolean"),
    "m": Unit((1, 0), 1.0, "m"),
    "s": Unit((0, 1), 1.0, "s"),
    "ms": Unit((0, 1), 0.001, "ms"),
    "m/s": Unit((1, -1), 1.0, "m/s"),
    "km/h": Unit((1, -1), 1 / 3.6, "km/h"),
    "m/s^2": Unit((1, -2), 1.0, "m/s^2"),
    "%": Unit((0, 0), 0.01, "%"),
    "degree": Unit((0, 0), 1.0, "degree"),
    "degree/s": Unit((0, -1), 1.0, "degree/s"),
    "m/(km/h)": Unit((0, 1), 3.6, "m/(km/h)"),
}

UNIT_ALIASES = {
    "1": "dimensionless",
    "unitless": "dimensionless",
    "无量纲": "dimensionless",
    "m/km/h": "m/(km/h)",
    "m per km/h": "m/(km/h)",
}


def normalize_standard_conversions(
    plan: SemanticPlan, signal_units: dict[str, str]
) -> SemanticPlan:
    return plan.model_copy(
        update={
            "requirements": [
                requirement.model_copy(
                    update={
                        "condition": _normalize_predicate(
                            requirement.condition, signal_units
                        ),
                        "trigger": _normalize_predicate(
                            requirement.trigger, signal_units
                        ),
                        "target": _normalize_predicate(
                            requirement.target, signal_units
                        ),
                        "scope": _normalize_predicate(
                            requirement.scope, signal_units
                        ),
                        "deadline": _normalize_numeric(
                            requirement.deadline, signal_units
                        ),
                    }
                )
                for requirement in plan.requirements
            ]
        }
    )


def _normalize_predicate(
    expression: PredicateExpression | None, signal_units: dict[str, str]
) -> PredicateExpression | None:
    if expression is None:
        return None
    return expression.model_copy(
        update={
            "left": _normalize_numeric(expression.left, signal_units),
            "right": _normalize_numeric(expression.right, signal_units),
            "operands": [
                _normalize_predicate(item, signal_units)
                for item in expression.operands
            ],
            "operand": _normalize_predicate(expression.operand, signal_units),
        }
    )


def _normalize_numeric(
    expression: NumericExpression | None, signal_units: dict[str, str]
) -> NumericExpression | None:
    if expression is None:
        return None
    left = _normalize_numeric(expression.left, signal_units)
    right = _normalize_numeric(expression.right, signal_units)
    operand = _normalize_numeric(expression.operand, signal_units)
    normalized = expression.model_copy(
        update={"left": left, "right": right, "operand": operand}
    )
    if (
        normalized.kind == "divide"
        and left is not None
        and right is not None
        and right.kind == "constant"
        and right.value is not None
        and abs(right.value - 3.6) < 1e-12
        and _numeric_declared_unit(left, signal_units) == "km/h"
    ):
        return NumericExpression(
            kind="convert", operand=left, target_unit="m/s"
        )
    return normalized


def _numeric_declared_unit(
    expression: NumericExpression, signal_units: dict[str, str]
) -> str | None:
    if expression.kind == "signal" and expression.name:
        return signal_units.get(expression.name)
    if expression.kind in {"constant", "parameter"}:
        return UNIT_ALIASES.get(
            (expression.unit or "").strip().lower(), expression.unit
        )
    if expression.kind == "convert":
        return expression.target_unit
    return None


class SemanticCompiler:
    def __init__(self, signal_units: dict[str, str]) -> None:
        self.signal_units = signal_units
        self.signals_used: set[str] = set()

    def compile(self, plan: SemanticPlan) -> STLResult:
        formulas: list[str] = []
        descriptions: list[str] = []
        mappings: list[TranslationFragment] = []
        for requirement in plan.requirements:
            formula, description, fragments = self._compile_requirement(requirement)
            formulas.append(formula)
            descriptions.append(description)
            mappings.extend(fragments)
        formula = formulas[0] if len(formulas) == 1 else " and ".join(f"({item})" for item in formulas)
        return STLResult(
            clarified_description="；".join(descriptions) + "。",
            formula=formula,
            explanation="该公式由通过类型和量纲检查的结构化语义模型确定性编译生成。",
            signals_used=sorted(self.signals_used),
            fragment_mappings=mappings,
        )

    def _compile_requirement(
        self, requirement: SemanticRequirement
    ) -> tuple[str, str, list[TranslationFragment]]:
        if requirement.kind == "invariant":
            if requirement.condition is None:
                raise SemanticValidationError("invariant 缺少 condition")
            condition = self._predicate(requirement.condition)
            body = condition
            description = f"在整个监测周期内，{self._predicate_nl(requirement.condition)}始终成立"
            mappings = [TranslationFragment(nl_fragment=self._predicate_nl(requirement.condition), stl_fragment=condition)]
            if requirement.scope is not None:
                scope = self._predicate(requirement.scope)
                body = f"({scope}) -> ({condition})"
                description = (
                    f"在整个监测周期内，当{self._predicate_nl(requirement.scope)}时，"
                    f"{self._predicate_nl(requirement.condition)}始终成立"
                )
                mappings.insert(0, TranslationFragment(nl_fragment=self._predicate_nl(requirement.scope), stl_fragment=scope))
            formula = f"always({body})"
            mappings.append(TranslationFragment(nl_fragment=description, stl_fragment=formula))
            return formula, description, mappings

        if requirement.kind == "response":
            if requirement.trigger is None or requirement.target is None or requirement.deadline is None:
                raise SemanticValidationError("response 必须包含 trigger、target 和 deadline")
            trigger = self._predicate(requirement.trigger)
            target = self._predicate(requirement.target)
            deadline, deadline_unit = self._numeric(requirement.deadline)
            if deadline_unit.dimensions != UNITS["s"].dimensions:
                raise SemanticValidationError(
                    f"response.deadline 必须是时间量纲，实际为 {deadline_unit.name}"
                )
            deadline_seconds = self._time_bound(requirement.deadline, deadline_unit)
            deadline_nl = self._numeric_nl(requirement.deadline)
            antecedent = trigger
            if requirement.scope is not None:
                scope = self._predicate(requirement.scope)
                antecedent = f"({scope}) and ({trigger})"
            response = f"eventually[0,{deadline_seconds}]({target})"
            formula = f"always(({antecedent}) -> ({response}))"
            description = (
                f"在整个监测周期内，如果{self._predicate_nl(requirement.trigger)}，"
                f"则必须在{deadline_nl}内使{self._predicate_nl(requirement.target)}成立"
            )
            mappings = [
                TranslationFragment(nl_fragment=self._predicate_nl(requirement.trigger), stl_fragment=trigger),
                TranslationFragment(nl_fragment=f"在{deadline_nl}内使{self._predicate_nl(requirement.target)}成立", stl_fragment=response),
                TranslationFragment(nl_fragment=description, stl_fragment=formula),
            ]
            return formula, description, mappings
        raise SemanticValidationError(f"不支持的 requirement kind: {requirement.kind}")

    def _predicate(self, expression: PredicateExpression) -> str:
        if expression.kind == "comparison":
            if expression.left is None or expression.right is None or expression.operator is None:
                raise SemanticValidationError("comparison 缺少 left、right 或 operator")
            left, left_unit = self._numeric(expression.left)
            right, right_unit = self._numeric(expression.right)
            if left_unit.dimensions != right_unit.dimensions:
                raise SemanticValidationError(
                    f"比较两侧量纲不一致：{left_unit.name} {expression.operator} {right_unit.name}"
                )
            if abs(left_unit.scale_to_si - right_unit.scale_to_si) > 1e-12:
                raise SemanticValidationError(
                    f"比较两侧单位尺度不同：{left_unit.name} 与 {right_unit.name}；请显式 convert"
                )
            if left_unit.name == "boolean" or right_unit.name == "boolean":
                if left_unit.name != right_unit.name or expression.operator not in {"==", "!="}:
                    raise SemanticValidationError("布尔信号只能与布尔值使用 == 或 != 比较")
            return f"{left} {expression.operator} {right}"
        if expression.kind in {"and", "or"}:
            if len(expression.operands) < 2:
                raise SemanticValidationError(f"{expression.kind} 至少需要两个 operands")
            joiner = f" {expression.kind} "
            return joiner.join(f"({self._predicate(item)})" for item in expression.operands)
        if expression.kind == "not":
            if expression.operand is None:
                raise SemanticValidationError("not 缺少 operand")
            return f"not ({self._predicate(expression.operand)})"
        raise SemanticValidationError(f"不支持的 predicate kind: {expression.kind}")

    def _numeric(self, expression: NumericExpression) -> tuple[str, Unit]:
        if expression.kind == "signal":
            if not expression.name or expression.name not in self.signal_units:
                raise SemanticValidationError(f"未知信号：{expression.name}")
            unit = self._unit(self.signal_units[expression.name])
            self.signals_used.add(expression.name)
            return expression.name, unit
        if expression.kind == "parameter":
            if not expression.name or not expression.unit:
                raise SemanticValidationError("parameter 必须包含 name 和 unit")
            return expression.name, self._unit(expression.unit)
        if expression.kind == "constant":
            if expression.value is None or not expression.unit:
                raise SemanticValidationError("constant 必须包含 value 和 unit")
            return self._number(expression.value), self._unit(expression.unit)
        if expression.kind in {"add", "subtract", "multiply", "divide"}:
            if expression.left is None or expression.right is None:
                raise SemanticValidationError(f"{expression.kind} 缺少 left 或 right")
            left, left_unit = self._numeric(expression.left)
            right, right_unit = self._numeric(expression.right)
            if expression.kind in {"add", "subtract"}:
                if left_unit.dimensions != right_unit.dimensions:
                    raise SemanticValidationError(
                        f"{expression.kind} 两侧量纲不一致：{left_unit.name} 与 {right_unit.name}"
                    )
                operator = "+" if expression.kind == "add" else "-"
                return f"({left} {operator} {right})", left_unit
            if expression.kind == "multiply":
                dimensions = tuple(a + b for a, b in zip(left_unit.dimensions, right_unit.dimensions))
                return f"({left} * {right})", Unit(dimensions, left_unit.scale_to_si * right_unit.scale_to_si, f"{left_unit.name}*{right_unit.name}")
            dimensions = tuple(a - b for a, b in zip(left_unit.dimensions, right_unit.dimensions))
            return f"({left} / {right})", Unit(dimensions, left_unit.scale_to_si / right_unit.scale_to_si, f"{left_unit.name}/{right_unit.name}")
        if expression.kind == "convert":
            if expression.operand is None or not expression.target_unit:
                raise SemanticValidationError("convert 必须包含 operand 和 target_unit")
            operand, source_unit = self._numeric(expression.operand)
            target_unit = self._unit(expression.target_unit)
            if source_unit.dimensions != target_unit.dimensions:
                raise SemanticValidationError(
                    f"不能将 {source_unit.name} 转换为 {target_unit.name}"
                )
            factor = source_unit.scale_to_si / target_unit.scale_to_si
            rendered = operand if abs(factor - 1) < 1e-12 else f"({operand} * {self._number(factor)})"
            return rendered, target_unit
        raise SemanticValidationError(f"不支持的 numeric kind: {expression.kind}")

    def _predicate_nl(self, expression: PredicateExpression) -> str:
        if expression.kind == "comparison":
            if expression.left is None or expression.right is None or expression.operator is None:
                raise SemanticValidationError("comparison 缺少 left、right 或 operator")
            operators = {
                "<": "小于",
                "<=": "小于等于",
                ">": "大于",
                ">=": "大于等于",
                "==": "等于",
                "!=": "不等于",
            }
            return (
                f"{self._numeric_nl(expression.left)}{operators[expression.operator]}"
                f"{self._numeric_nl(expression.right)}"
            )
        if expression.kind in {"and", "or"}:
            joiner = "并且" if expression.kind == "and" else "或者"
            return joiner.join(self._predicate_nl(item) for item in expression.operands)
        if expression.kind == "not" and expression.operand is not None:
            return f"不满足“{self._predicate_nl(expression.operand)}”"
        raise SemanticValidationError(f"无法生成自然语言的 predicate kind: {expression.kind}")

    def _numeric_nl(self, expression: NumericExpression) -> str:
        if expression.kind in {"signal", "parameter"}:
            return expression.name or "<未命名>"
        if expression.kind == "constant":
            if expression.value is None or not expression.unit:
                raise SemanticValidationError("constant 必须包含 value 和 unit")
            suffix = "" if expression.unit in {"dimensionless", "boolean"} else f" {expression.unit}"
            return f"{self._number(expression.value)}{suffix}"
        if expression.kind in {"add", "subtract", "multiply", "divide"}:
            if expression.left is None or expression.right is None:
                raise SemanticValidationError(f"{expression.kind} 缺少 left 或 right")
            operators = {"add": "+", "subtract": "-", "multiply": "×", "divide": "÷"}
            return (
                f"({self._numeric_nl(expression.left)} {operators[expression.kind]} "
                f"{self._numeric_nl(expression.right)})"
            )
        if expression.kind == "convert":
            if expression.operand is None or not expression.target_unit:
                raise SemanticValidationError("convert 必须包含 operand 和 target_unit")
            return f"换算为 {expression.target_unit} 的 {self._numeric_nl(expression.operand)}"
        raise SemanticValidationError(f"无法生成自然语言的 numeric kind: {expression.kind}")

    def _time_bound(self, expression: NumericExpression, unit: Unit) -> str:
        rendered, _ = self._numeric(expression)
        if expression.kind == "constant" and expression.value is not None:
            return self._number(expression.value * unit.scale_to_si)
        if abs(unit.scale_to_si - 1) < 1e-12:
            return rendered
        return f"({rendered} * {self._number(unit.scale_to_si)})"

    @staticmethod
    def _number(value: float) -> str:
        return str(int(value)) if value.is_integer() else f"{value:g}"

    @staticmethod
    def _unit(name: str) -> Unit:
        normalized = name.strip().lower().replace("％", "%")
        normalized = UNIT_ALIASES.get(normalized, normalized)
        unit = UNITS.get(normalized)
        if unit is None:
            raise SemanticValidationError(f"不支持或未知单位：{name}")
        return unit


def validate_plan_provenance(
    plan: SemanticPlan,
    clarifications: list[Clarification],
    original_text: str = "",
) -> None:
    by_id = {item.ambiguity_id: item for item in clarifications}
    covered = {
        clarification_id
        for requirement in plan.requirements
        for clarification_id in requirement.clarification_ids
    }
    unknown = sorted(covered - by_id.keys())
    if unknown:
        raise SemanticValidationError(
            f"SemanticPlan 引用了不存在的澄清 ID：{', '.join(unknown)}"
        )
    missing = sorted(by_id.keys() - covered)
    if missing:
        raise SemanticValidationError(
            f"SemanticPlan 未覆盖已确认澄清：{', '.join(missing)}"
        )
    for clarification in clarifications:
        matching = [
            requirement
            for requirement in plan.requirements
            if clarification.ambiguity_id in requirement.clarification_ids
        ]
        if clarification.semantic_role == "response_deadline" and not any(
            item.kind == "response" and item.deadline is not None for item in matching
        ):
            raise SemanticValidationError(
                f"澄清 {clarification.ambiguity_id} 是响应时限，必须进入 response.deadline"
            )
        if clarification.semantic_role == "response_trigger" and not any(
            item.kind == "response" and item.trigger is not None for item in matching
        ):
            raise SemanticValidationError(
                f"澄清 {clarification.ambiguity_id} 是响应触发条件，必须进入 response.trigger"
            )
        if clarification.semantic_role == "scope" and "整个信号监测周期" not in clarification.answer:
            if not any(item.scope is not None for item in matching):
                raise SemanticValidationError(
                    f"澄清 {clarification.ambiguity_id} 是作用域，必须进入 requirement.scope"
                )
    for requirement in plan.requirements:
        expressions = [
            requirement.condition,
            requirement.trigger,
            requirement.target,
            requirement.scope,
        ]
        for expression in expressions:
            if expression is not None:
                _validate_predicate_provenance(
                    expression, requirement.clarification_ids, by_id, original_text
                )
        if requirement.deadline is not None:
            _validate_numeric_provenance(
                requirement.deadline,
                requirement.clarification_ids,
                by_id,
                original_text,
            )


def _validate_predicate_provenance(
    expression: PredicateExpression,
    requirement_ids: list[str],
    clarifications: dict[str, Clarification],
    original_text: str,
) -> None:
    for numeric in (expression.left, expression.right):
        if numeric is not None:
            _validate_numeric_provenance(
                numeric, requirement_ids, clarifications, original_text
            )
    for operand in expression.operands:
        _validate_predicate_provenance(
            operand, requirement_ids, clarifications, original_text
        )
    if expression.operand is not None:
        _validate_predicate_provenance(
            expression.operand, requirement_ids, clarifications, original_text
        )


def _validate_numeric_provenance(
    expression: NumericExpression,
    requirement_ids: list[str],
    clarifications: dict[str, Clarification],
    original_text: str,
) -> None:
    if expression.kind == "constant" and expression.unit != "boolean":
        source_id, source_text = _source_text(
            expression, requirement_ids, clarifications, original_text
        )
        if expression.value is None or not expression.unit:
            raise SemanticValidationError("constant 缺少 value 或 unit")
        if not _answer_contains_number(source_text, expression.value):
            raise SemanticValidationError(
                f"常量 {expression.value:g} 未出现在来源 {source_id} 中"
            )
        if expression.value != 0 and not _answer_contains_unit(source_text, expression.unit):
            raise SemanticValidationError(
                f"单位 {expression.unit} 未出现在来源 {source_id} 中，禁止自行补全"
            )
    if expression.kind == "parameter":
        source_id, source_text = _source_text(
            expression, requirement_ids, clarifications, original_text
        )
        if not expression.name or expression.name not in source_text:
            raise SemanticValidationError(
                f"参数 {expression.name} 未出现在来源 {source_id} 中"
            )
        if not expression.unit or not _answer_contains_unit(source_text, expression.unit):
            raise SemanticValidationError(
                f"参数 {expression.name} 的单位 {expression.unit} 未出现在来源 {source_id} 中"
            )
    for child in (expression.left, expression.right, expression.operand):
        if child is not None:
            _validate_numeric_provenance(
                child, requirement_ids, clarifications, original_text
            )


def _source_text(
    expression: NumericExpression,
    requirement_ids: list[str],
    clarifications: dict[str, Clarification],
    original_text: str,
) -> tuple[str, str]:
    source_id = expression.source_clarification_id
    if source_id == "original":
        if not original_text:
            raise SemanticValidationError("source_clarification_id=original 但原始需求为空")
        return source_id, original_text
    if not source_id or source_id not in clarifications:
        raise SemanticValidationError(
            f"{expression.kind} {expression.name or expression.value} 缺少有效 source_clarification_id"
        )
    if source_id not in requirement_ids:
        raise SemanticValidationError(
            f"source_clarification_id {source_id} 未列入 requirement.clarification_ids"
        )
    source = clarifications[source_id]
    return source_id, f"{source.answer} {source.supporting_text}"


def _answer_contains_number(answer: str, value: float) -> bool:
    rendered = str(int(value)) if value.is_integer() else f"{value:g}"
    if rendered in answer:
        return True
    chinese = {0: "零", 1: "一", 2: "两", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    return value.is_integer() and int(value) in chinese and chinese[int(value)] in answer


def _answer_contains_unit(answer: str, unit: str) -> bool:
    unit = UNIT_ALIASES.get(unit.strip().lower(), unit.strip().lower())
    aliases = {
        "s": ("秒", " s", "[s]", "时间头距", "响应时间", "时限"),
        "ms": ("毫秒", " ms"),
        "m": ("米", " m", "[m]", "距离"),
        "km/h": ("km/h", "时速", "速度"),
        "m/s": ("m/s", "米每秒"),
        "dimensionless": ("无量纲", "倍"),
        "m/(km/h)": (
            "m/(km/h)",
            "米/(km/h)",
            "每增加 1 km/h",
            "每1km/h",
            "倍时速距离",
            "倍速度距离",
        ),
        "%": ("%", "百分比"),
    }
    if unit == "m/(km/h)" and "倍" in answer:
        return any(token in answer for token in ("时速", "速度")) and any(
            token in answer for token in ("距离", "米", "front_vehicle_distance")
        )
    if unit == "m/(km/h)" and any(token in answer for token in ("乘以", "×", "*")):
        return any(token in answer for token in ("时速", "速度", "ego_speed")) and any(
            token in answer for token in ("距离", "米", "front_vehicle_distance")
        )
    return any(alias in answer for alias in aliases.get(unit, (unit,)))
