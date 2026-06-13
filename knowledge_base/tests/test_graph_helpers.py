from stl_clarifier.graph import (
    advance_state,
    candidate_quality_problem,
    ensure_required_ambiguities,
    generate_local_candidates,
    local_evidence_problem,
    resolve_answer,
    validate_formula,
)
from stl_clarifier.schemas import Ambiguity, Candidate, SourceType
from stl_clarifier.services import extract_json_object


SIGNAL = "ego_speed"


def candidates() -> list[Candidate]:
    return [
        Candidate(
            id="speed_4",
            value=f"{SIGNAL} <= 4",
            explanation="保守低速",
            source_type=SourceType.LLM_INFERENCE,
            source_reference="工程推断",
        ),
        Candidate(
            id="speed_10",
            value=f"{SIGNAL} <= 10",
            explanation="宽松低速",
            source_type=SourceType.TAVILY,
            source_reference="https://example.com",
        ),
    ]


def test_resolve_numeric_selection() -> None:
    answer, selected = resolve_answer("1", candidates())
    assert answer.endswith("<= 4")
    assert selected is not None and selected.id == "speed_4"


def test_resolve_custom_input() -> None:
    answer, selected = resolve_answer("速度不超过 6 km/h", candidates())
    assert answer == "速度不超过 6 km/h"
    assert selected is None


def test_validate_formula_accepts_known_signal() -> None:
    formula = f"always({SIGNAL} <= 4)"
    assert validate_formula(formula, [SIGNAL], {SIGNAL}) == []


def test_validate_formula_rejects_parenthesis_and_unknown_signal() -> None:
    unknown = "Autonomous_Driving_Parking_fake_signal"
    errors = validate_formula(f"always(({unknown} <= 4)", [unknown], {SIGNAL})
    assert any("左括号" in error for error in errors)
    assert any("不得拼接场景前缀" in error for error in errors)
    assert any("不存在的信号" in error for error in errors)


def test_required_ambiguities_are_not_silently_inferred() -> None:
    ambiguities = ensure_required_ambiguities(
        "整个泊车过程中，车辆应始终保持低速", [], []
    )
    assert [item.category for item in ambiguities] == ["threshold", "scope", "time"]


def test_dynamic_speed_limit_is_not_treated_as_numeric_threshold() -> None:
    model_ambiguity = {
        "id": "speed_limit_value",
        "description": "限速数值不明确",
        "question": "限速是多少？",
        "category": "threshold",
        "knowledge_query": "限速数值",
    }
    ambiguities = ensure_required_ambiguities(
        "不管什么情形，车辆始终不得超过限速",
        [Ambiguity.model_validate(model_ambiguity)],
        [],
    )
    assert [item.category for item in ambiguities] == ["time"]


def test_safe_distance_braking_sentence_keeps_three_distinct_vague_points() -> None:
    ambiguities = ensure_required_ambiguities(
        "自车应与前车保持安全距离，并在必要的时候及时刹车", [], []
    )
    ids = {item.id for item in ambiguities}
    assert "define_safe_distance" in ids
    assert "define_braking_trigger" in ids
    assert "define_braking_response_deadline" in ids
    assert all(
        item.issue_type == "vagueness"
        for item in ambiguities
        if item.id in {
            "define_safe_distance",
            "define_braking_trigger",
            "define_braking_response_deadline",
        }
    )


def test_resolved_category_is_not_asked_again() -> None:
    ambiguities = ensure_required_ambiguities(
        "整个泊车过程中，车辆应始终保持低速",
        [],
        [{"category": "threshold"}, {"category": "scope"}],
    )
    assert [item.category for item in ambiguities] == ["time"]


def test_extract_json_object_from_code_fence() -> None:
    assert extract_json_object('```json\n{"value": "OK"}\n```') == '{"value": "OK"}'


def test_extract_json_object_ignores_surrounding_text() -> None:
    assert extract_json_object('结果如下：{"value": "OK"} 完成') == '{"value": "OK"}'


def test_parking_scope_prefers_parking_mode() -> None:
    result = generate_local_candidates(
        {
            "original_text": "整个泊车过程中车辆应保持低速",
            "current_ambiguity": {
                "id": "scope",
                "description": "scope",
                "question": "scope?",
                "category": "scope",
                "knowledge_query": "scope",
            },
            "local_source_ids": [
                "signals_kb.txt#Autonomous_Driving/Parking/brake_active",
                "signals_kb.txt#Autonomous_Driving/Parking/parking_mode",
                "signals_kb.txt#Autonomous_Driving/Parking/parking_completed_event",
            ],
        }
    )
    assert result[0].value == "在 parking_mode == 1 期间"


def test_parking_word_prefers_parking_mode() -> None:
    result = generate_local_candidates(
        {
            "original_text": "整个停车过程中车辆应保持低速",
            "current_ambiguity": {
                "id": "scope",
                "description": "scope",
                "question": "scope?",
                "category": "scope",
                "knowledge_query": "scope",
            },
            "local_source_ids": [
                "signals_kb.txt#Autonomous_Driving/Parking/parking_mode",
                "signals_kb.txt#Autonomous_Driving/Parking/parking_completed_event",
            ],
        }
    )
    assert result[0].value == "在 parking_mode == 1 期间"
    assert "parking_completed_event" in result[1].value


def test_langgraph_selects_first_ambiguity_without_network() -> None:
    state = advance_state(
        {
            "original_text": "test",
            "ambiguities": [
                {
                    "id": "threshold",
                    "description": "threshold",
                    "question": "threshold?",
                    "category": "threshold",
                    "knowledge_query": "threshold",
                }
            ],
            "clarifications": [],
        }
    )
    assert state["current_ambiguity"]["id"] == "threshold"


def test_rejects_vague_fixed_value_candidate_without_value() -> None:
    ambiguity = Ambiguity(
        id="safe_distance",
        issue_type="vagueness",
        description="安全距离不明确",
        question="安全距离是多少？",
        category="threshold",
        knowledge_query="安全距离",
    )
    candidate = Candidate(
        id="fixed",
        candidate_type="formula",
        value="固定数值安全距离",
        explanation="使用固定值",
        source_type=SourceType.SIGNAL_KNOWLEDGE,
        source_reference="signals_kb.txt#x/front_vehicle_distance",
    )
    assert candidate_quality_problem(ambiguity, candidate, {"front_vehicle_distance"})


def test_accepts_parameterized_signal_threshold_candidate() -> None:
    ambiguity = Ambiguity(
        id="safe_distance",
        issue_type="vagueness",
        description="安全距离不明确",
        question="安全距离是多少？",
        category="threshold",
        knowledge_query="安全距离",
    )
    candidate = Candidate(
        id="parameterized_distance",
        candidate_type="parameterized",
        value="front_vehicle_distance >= d_safe",
        explanation="使用可配置安全距离参数",
        parameters=["d_safe"],
        source_type=SourceType.LLM_INFERENCE,
        source_reference="LLM 工程推断",
    )
    assert candidate_quality_problem(ambiguity, candidate, {"front_vehicle_distance"}) is None


def test_rejects_numeric_value_not_supported_by_local_evidence() -> None:
    candidate = Candidate(
        id="invented_10m",
        candidate_type="formula",
        value="front_vehicle_distance >= 10 m",
        explanation="固定安全距离",
        source_type=SourceType.SIGNAL_KNOWLEDGE,
        source_reference="signals_kb.txt#Autonomous_Driving/ACC/front_vehicle_distance",
    )
    problem = local_evidence_problem(
        candidate,
        "信号名=front_vehicle_distance；自车与前车之间的纵向距离；单位 m。",
    )
    assert problem is not None and "未提供数值" in problem
