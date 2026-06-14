from __future__ import annotations

import pytest

from stl_clarifier.schemas import (
    Clarification,
    NumericExpression,
    PredicateExpression,
    SemanticPlan,
    SemanticRequirement,
)
from stl_clarifier.schemas import SourceType
from stl_clarifier.semantics import (
    SemanticCompiler,
    SemanticValidationError,
    normalize_standard_conversions,
    validate_plan_provenance,
)


SIGNAL_UNITS = {
    "ego_speed": "km/h",
    "front_vehicle_distance": "m",
    "front_vehicle_closing_speed": "km/h",
    "brake_active": "boolean",
}


def signal(name: str) -> NumericExpression:
    return NumericExpression(kind="signal", name=name)


def constant(value: float, unit: str) -> NumericExpression:
    return NumericExpression(kind="constant", value=value, unit=unit)


def comparison(
    left: NumericExpression, operator: str, right: NumericExpression
) -> PredicateExpression:
    return PredicateExpression(
        kind="comparison", left=left, operator=operator, right=right
    )


def test_dimension_checker_rejects_distance_compared_with_speed_times_scalar() -> None:
    unsafe_distance = NumericExpression(
        kind="multiply",
        left=signal("ego_speed"),
        right=constant(2, "dimensionless"),
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                condition=comparison(
                    signal("front_vehicle_distance"), ">=", unsafe_distance
                ),
            )
        ]
    )

    with pytest.raises(SemanticValidationError, match="量纲不一致"):
        SemanticCompiler(SIGNAL_UNITS).compile(plan)


def test_speed_to_distance_ratio_compiles_as_user_defined_numeric_mapping() -> None:
    ratio = NumericExpression(
        kind="constant",
        value=2,
        unit="m/(km/h)",
        source_clarification_id="safe_distance",
    )
    safe_distance = NumericExpression(
        kind="multiply", left=ratio, right=signal("ego_speed")
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["safe_distance"],
                condition=comparison(
                    signal("front_vehicle_distance"), ">=", safe_distance
                ),
            )
        ]
    )
    clarification_item = clarification(
        "safe_distance", "安全距离采用两倍时速距离"
    )

    validate_plan_provenance(plan, [clarification_item])
    result = SemanticCompiler(SIGNAL_UNITS).compile(plan)

    assert result.formula == "always(front_vehicle_distance >= (2 * ego_speed))"
    assert "2 m/(km/h)" in result.clarified_description


def test_dimensionless_unit_alias_one_is_supported() -> None:
    expression = NumericExpression(
        kind="multiply",
        left=constant(2, "1"),
        right=constant(3, "dimensionless"),
    )
    predicate = comparison(expression, "==", constant(6, "unitless"))

    assert SemanticCompiler({})._predicate(predicate) == "(2 * 3) == 6"


def test_explicit_speed_conversion_times_headway_compiles_to_distance() -> None:
    speed_mps = NumericExpression(
        kind="convert", operand=signal("ego_speed"), target_unit="m/s"
    )
    safe_distance = NumericExpression(
        kind="multiply", left=speed_mps, right=constant(2, "s")
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                condition=comparison(
                    signal("front_vehicle_distance"), ">=", safe_distance
                ),
            )
        ]
    )

    result = SemanticCompiler(SIGNAL_UNITS).compile(plan)

    assert "ego_speed * 0.277778" in result.formula
    assert "* 2" in result.formula
    assert "换算为 m/s" in result.clarified_description


def test_divide_by_3_6_is_normalized_as_unit_conversion_not_business_constant() -> None:
    arithmetic_conversion = NumericExpression(
        kind="divide",
        left=signal("ego_speed"),
        right=NumericExpression(
            kind="constant",
            value=3.6,
            unit="1",
            source_clarification_id="original",
        ),
    )
    headway = NumericExpression(
        kind="parameter",
        name="T",
        unit="s",
        source_clarification_id="safe_distance",
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["safe_distance"],
                condition=comparison(
                    signal("front_vehicle_distance"),
                    ">=",
                    NumericExpression(
                        kind="multiply", left=arithmetic_conversion, right=headway
                    ),
                ),
            )
        ]
    )
    safe_distance = Clarification(
        ambiguity_id="safe_distance",
        category="threshold",
        question="安全距离是多少？",
        answer="front_vehicle_distance >= ego_speed / 3.6 * T",
        supporting_text="T 为安全时间头距阈值，单位为 s",
        source_type=SourceType.LLM_INFERENCE,
        source_reference="LLM 工程推断",
    )

    normalized = normalize_standard_conversions(plan, SIGNAL_UNITS)
    validate_plan_provenance(normalized, [safe_distance], "保持安全距离")
    result = SemanticCompiler(SIGNAL_UNITS).compile(normalized)

    assert "ego_speed * 0.277778" in result.formula
    assert "3.6" not in result.formula


def test_response_is_deterministically_compiled_with_eventually() -> None:
    trigger = PredicateExpression(
        kind="and",
        operands=[
            comparison(
                signal("front_vehicle_distance"),
                "<",
                NumericExpression(kind="parameter", name="d_brake", unit="m"),
            ),
            comparison(
                signal("front_vehicle_closing_speed"), ">", constant(0, "km/h")
            ),
        ],
    )
    target = comparison(signal("brake_active"), "==", constant(1, "boolean"))
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="response",
                trigger=trigger,
                target=target,
                deadline=constant(0.3, "s"),
            )
        ]
    )

    result = SemanticCompiler(SIGNAL_UNITS).compile(plan)

    assert "eventually[0,0.3](brake_active == 1)" in result.formula
    assert "always[0,0.3]" not in result.formula
    assert result.formula.startswith("always(")
    assert "0.3 s内" in result.clarified_description


def test_response_deadline_must_have_time_dimension() -> None:
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="response",
                trigger=comparison(
                    signal("front_vehicle_distance"),
                    "<",
                    NumericExpression(kind="parameter", name="d_brake", unit="m"),
                ),
                target=comparison(
                    signal("brake_active"), "==", constant(1, "boolean")
                ),
                deadline=constant(15, "km/h"),
            )
        ]
    )

    with pytest.raises(SemanticValidationError, match="时间量纲"):
        SemanticCompiler(SIGNAL_UNITS).compile(plan)


def clarification(ambiguity_id: str, answer: str) -> Clarification:
    return Clarification(
        ambiguity_id=ambiguity_id,
        category="threshold",
        question="test",
        answer=answer,
        source_type=SourceType.USER_INPUT,
        source_reference="用户输入",
    )


def test_provenance_rejects_invented_time_unit_for_two_times_speed() -> None:
    speed_mps = NumericExpression(
        kind="convert", operand=signal("ego_speed"), target_unit="m/s"
    )
    invented_headway = constant(2, "s").model_copy(
        update={"source_clarification_id": "safe_distance"}
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["safe_distance"],
                condition=comparison(
                    signal("front_vehicle_distance"),
                    ">=",
                    NumericExpression(
                        kind="multiply", left=speed_mps, right=invented_headway
                    ),
                ),
            )
        ]
    )

    with pytest.raises(SemanticValidationError, match="单位 s 未出现在"):
        validate_plan_provenance(
            plan, [clarification("safe_distance", "安全距离采用两倍时速")]
        )


def test_provenance_accepts_explicit_two_second_headway() -> None:
    speed_mps = NumericExpression(
        kind="convert", operand=signal("ego_speed"), target_unit="m/s"
    )
    headway = constant(2, "s").model_copy(
        update={"source_clarification_id": "safe_distance"}
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["safe_distance"],
                condition=comparison(
                    signal("front_vehicle_distance"),
                    ">=",
                    NumericExpression(kind="multiply", left=speed_mps, right=headway),
                ),
            )
        ]
    )

    validate_plan_provenance(
        plan,
        [
            clarification(
                "safe_distance",
                "采用 2 秒时间头距：front_vehicle_distance >= ego_speed / 3.6 * 2",
            )
        ],
    )


def test_response_deadline_role_cannot_be_hidden_in_invariant() -> None:
    deadline = Clarification(
        ambiguity_id="brake_deadline",
        category="time",
        question="多长时间内刹车？",
        answer="0.3 s",
        semantic_role="response_deadline",
        source_type=SourceType.USER_INPUT,
        source_reference="用户输入",
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["brake_deadline"],
                condition=comparison(
                    signal("brake_active"), "==", constant(1, "boolean")
                ),
            )
        ]
    )

    with pytest.raises(SemanticValidationError, match="response.deadline"):
        validate_plan_provenance(plan, [deadline])


def test_explicit_constant_can_be_traced_to_original_requirement() -> None:
    limit = NumericExpression(
        kind="constant",
        value=5,
        unit="km/h",
        source_clarification_id="original",
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                condition=comparison(signal("ego_speed"), "<=", limit),
            )
        ]
    )

    validate_plan_provenance(
        plan, [], "在整个泊车过程中，自车速度不超过 5 km/h"
    )
