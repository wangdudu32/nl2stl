from pathlib import Path

from stl_clarifier.knowledge import KnowledgeBase
from stl_clarifier.schemas import (
    Ambiguity,
    AnswerAssessment,
    Candidate,
    CandidateAssessment,
    CandidateReview,
    CandidateReviewSet,
    CandidateSet,
    Clarification,
    DomainContext,
    NumericExpression,
    PredicateExpression,
    SearchResult,
    SearchRelevanceAssessment,
    SemanticPlan,
    SemanticRequirement,
    SourceType,
)
from stl_clarifier.workflow import ClarificationWorkflow


ROOT = Path(__file__).resolve().parents[1]


class FakeChat:
    def __init__(self, assessments: list[object]) -> None:
        self.assessments = assessments
        self.calls = 0

    def generate(self, schema, system, user):
        self.calls += 1
        return self.assessments.pop(0)

    def close(self) -> None:
        pass


class FakeTavily:
    def close(self) -> None:
        pass


def threshold_ambiguity() -> Ambiguity:
    return Ambiguity(
        id="low_speed",
        description="低速阈值不明确",
        question="低速是多少？",
        category="threshold",
        knowledge_query="停车低速阈值",
    )


def scope_ambiguity() -> Ambiguity:
    return Ambiguity(
        id="intersection_scope",
        description="车辆通过路口期间的起止范围不明确",
        question="通过路口期间如何定义？",
        category="scope",
        knowledge_query="路口通过过程范围",
    )


def threshold_candidates() -> list[Candidate]:
    return [
        Candidate(
            id="speed_5",
            value="ego_speed <= 5 km/h",
            explanation="保守阈值",
            source_type=SourceType.LLM_INFERENCE,
            source_reference="工程推断",
        ),
        Candidate(
            id="speed_10",
            value="ego_speed <= 10 km/h",
            explanation="宽松阈值",
            source_type=SourceType.LLM_INFERENCE,
            source_reference="工程推断",
        ),
    ]


def vehicle_context() -> DomainContext:
    return DomainContext(
        domain="自动驾驶",
        scene="道路限速控制",
        subject="车辆",
        quantities=["自车速度", "道路限速"],
        expected_units=["km/h"],
        search_keywords=["汽车", "道路交通"],
    )


def build_workflow(chat: FakeChat, messages: list[str]) -> ClarificationWorkflow:
    return ClarificationWorkflow(
        chat,
        FakeTavily(),
        KnowledgeBase(ROOT / "signals_kb.txt", ROOT / "stl_operators.md"),
        messages.append,
    )


def test_custom_answer_is_reasked_until_it_resolves_ambiguity() -> None:
    chat = FakeChat(
        [
            AnswerAssessment(
                resolves_ambiguity=False,
                reason="仍然没有数值和单位",
                follow_up_question="请给出 km/h 数值",
            ),
            AnswerAssessment(
                resolves_ambiguity=True,
                normalized_answer="ego_speed <= 5 km/h",
                reason="数值、方向和单位明确",
            ),
        ]
    )
    messages: list[str] = []
    answers = iter(["低一点", "5 km/h"])
    workflow = build_workflow(chat, messages)

    value, selected = workflow._obtain_valid_answer(
        "停车时保持低速",
        vehicle_context(),
        threshold_ambiguity(),
        threshold_candidates(),
        "信号名=ego_speed；单位 km/h",
        lambda _ambiguity, _candidates: next(answers),
    )

    assert value == "ego_speed <= 5 km/h"
    assert selected is None
    assert chat.calls == 2
    assert any("未能解决" in message for message in messages)


def test_selecting_candidate_skips_custom_answer_validation() -> None:
    chat = FakeChat([])
    workflow = build_workflow(chat, [])

    value, selected = workflow._obtain_valid_answer(
        "停车时保持低速",
        vehicle_context(),
        threshold_ambiguity(),
        threshold_candidates(),
        "",
        lambda _ambiguity, _candidates: "1",
    )

    assert value == "ego_speed <= 5 km/h"
    assert selected is not None and selected.id == "speed_5"
    assert chat.calls == 0


def test_search_query_uses_analyzed_domain_and_scene() -> None:
    query = ClarificationWorkflow._build_search_query(
        "车辆始终不得超过限速", vehicle_context(), threshold_ambiguity()
    )
    assert "自动驾驶" in query
    assert "道路限速控制" in query
    assert "km/h" in query
    assert "网络设备" not in query


def test_llm_relevance_selection_uses_domain_context() -> None:
    results = [
        SearchResult(
            title="CDN 单请求限速",
            url="https://example.com/cdn",
            content="最低 100 KB/s 带宽限制",
        ),
        SearchResult(
            title="道路车辆速度限制",
            url="https://example.com/car",
            content="汽车道路行驶速度单位 km/h",
        ),
        SearchResult(
            title="协议报文限速",
            url="https://example.com/pps",
            content="网络设备每秒 102400 pps",
        ),
    ]
    chat = FakeChat(
        [
            SearchRelevanceAssessment(
                relevant_urls=["https://example.com/car"],
                reason="只有道路车辆速度结果符合自动驾驶场景和 km/h 单位",
            )
        ]
    )
    workflow = build_workflow(chat, [])
    filtered = workflow._select_relevant_web_results(
        vehicle_context(), threshold_ambiguity(), results
    )
    assert [item.url for item in filtered] == ["https://example.com/car"]


def test_packet_rate_can_be_relevant_in_network_device_domain() -> None:
    packet = SearchResult(
        title="协议报文限速",
        url="https://example.com/pps",
        content="网络设备每秒 102400 pps",
    )
    context = DomainContext(
        domain="网络设备",
        scene="协议报文流量控制",
        subject="交换机",
        quantities=["报文速率"],
        expected_units=["pps"],
        search_keywords=["网络设备", "协议报文"],
    )
    chat = FakeChat(
        [
            SearchRelevanceAssessment(
                relevant_urls=[packet.url],
                reason="报文速率和 pps 与网络设备场景一致",
            )
        ]
    )
    workflow = build_workflow(chat, [])
    filtered = workflow._select_relevant_web_results(
        context, threshold_ambiguity(), [packet]
    )
    assert filtered == [packet]


def test_custom_answer_cannot_add_temporal_operator_to_threshold() -> None:
    workflow = build_workflow(FakeChat([]), [])
    problem = workflow._normalized_answer_problem(
        threshold_ambiguity(), "always(ego_speed <= 180 km/h)"
    )
    assert problem is not None and "时序算子" in problem


def test_scope_answer_can_express_whole_monitoring_period_with_always() -> None:
    workflow = build_workflow(FakeChat([]), [])
    problem = workflow._normalized_answer_problem(
        scope_ambiguity(), "always，即过程范围采用整个信号监测周期"
    )
    assert problem is None


def test_custom_whole_period_scope_answer_is_accepted() -> None:
    chat = FakeChat(
        [
            AnswerAssessment(
                resolves_ambiguity=True,
                normalized_answer="过程范围采用整个信号监测周期",
                reason="用户明确选择了整个观察期间",
            )
        ]
    )
    workflow = build_workflow(chat, [])

    value, selected = workflow._obtain_valid_answer(
        "车辆通过路口期间，车速应始终保持低速",
        vehicle_context(),
        scope_ambiguity(),
        [],
        "",
        lambda _ambiguity, _candidates: "整个观察期间",
    )

    assert value == "过程范围采用整个信号监测周期"
    assert selected is None
    assert chat.calls == 1


def test_combined_distance_and_braking_scene_binds_to_aeb() -> None:
    context = DomainContext(
        domain="自动驾驶",
        scene="车距保持与制动控制",
        subject="自车",
        quantities=["前车距离", "制动"],
        expected_units=["m"],
        search_keywords=["AEB", "ACC"],
        knowledge_scenes=["ACC", "AEB"],
    )
    assert ClarificationWorkflow._resolve_knowledge_scenes(context) == ["AEB"]


def test_parameterized_fallbacks_do_not_abort_safe_distance_flow() -> None:
    workflow = build_workflow(FakeChat([]), [])
    context = DomainContext(
        domain="自动驾驶",
        scene="AEB",
        subject="自车",
        knowledge_scenes=["AEB"],
    )
    ambiguity = Ambiguity(
        id="define_safe_distance",
        issue_type="vagueness",
        description="安全距离不明确",
        question="安全距离是多少？",
        category="threshold",
        knowledge_query="安全距离",
    )
    candidates = workflow._deterministic_parameterized_fallbacks(
        context,
        ambiguity,
        [
            "signals_kb.txt#Autonomous_Driving/AEB/front_vehicle_distance",
            "signals_kb.txt#Autonomous_Driving/AEB/ttc",
        ],
    )
    assert len(candidates) >= 2
    assert candidates[0].value == "front_vehicle_distance >= d_safe"
    assert candidates[1].value == "ttc >= ttc_safe"


def test_local_knowledge_candidates_have_priority_over_search() -> None:
    local_candidates = [
        Candidate(
            id="direct_limit",
            value="ego_speed <= speed_limit",
            explanation="直接比较自车速度和动态道路限速",
            source_type=SourceType.SIGNAL_KNOWLEDGE,
            source_reference="signals_kb.txt#Autonomous_Driving/Speed_Limit/speed_limit",
        ),
        Candidate(
            id="margin_limit",
            value="speeding_margin <= 0",
            explanation="使用知识库中的超速差值派生信号",
            source_type=SourceType.SIGNAL_KNOWLEDGE,
            source_reference="signals_kb.txt#Autonomous_Driving/Speed_Limit/speeding_margin",
        ),
    ]
    chat = FakeChat(
        [
            CandidateAssessment(
                local_knowledge_sufficient=True,
                candidates=local_candidates,
            )
        ]
    )
    messages: list[str] = []
    workflow = build_workflow(chat, messages)
    ambiguity = Ambiguity(
        id="confirm_signal_mapping",
        description="确认限速信号映射",
        question="选择表达方式",
        category="signal",
        knowledge_query="限速信号",
    )
    source_ids = [
        "signals_kb.txt#Autonomous_Driving/Speed_Limit/ego_speed",
        *[item.source_reference for item in local_candidates],
    ]

    result = workflow._local_knowledge_candidates(
        vehicle_context(),
        ambiguity,
        "speeding_margin = ego_speed - speed_limit；正值表示超速，0 表示未超速边界",
        source_ids,
    )

    assert [item.value for item in result] == [
        "ego_speed <= speed_limit",
        "speeding_margin <= 0",
    ]
    assert all(item.source_type == SourceType.SIGNAL_KNOWLEDGE for item in result)
    assert "Speed_Limit/ego_speed" in result[0].source_reference
    assert "Speed_Limit/speed_limit" in result[0].source_reference
    assert any("无需外部搜索" in message for message in messages)


def test_safe_distance_review_rejects_braking_trigger_candidate() -> None:
    workflow = build_workflow(FakeChat([]), [])
    ambiguity = Ambiguity(
        id="define_safe_distance",
        issue_type="vagueness",
        description="安全距离没有明确的定义",
        question="安全距离是多少？",
        category="threshold",
        knowledge_query="安全距离",
    )
    candidate = Candidate(
        id="wrong_braking_rule",
        candidate_type="parameterized",
        value="brake_active = (front_vehicle_distance < safe_distance)",
        explanation="距离不足时触发刹车",
        parameters=["safe_distance"],
        source_type=SourceType.LLM_INFERENCE,
        source_reference="LLM 工程推断",
    )

    problem = workflow._candidate_semantic_problem(ambiguity, candidate)

    assert problem is not None and "安全距离问题" in problem


def test_response_deadline_review_rejects_unrelated_numbers() -> None:
    workflow = build_workflow(FakeChat([]), [])
    ambiguity = Ambiguity(
        id="define_braking_response_deadline",
        issue_type="vagueness",
        description="及时刹车缺少响应时限",
        question="多长时间内刹车？",
        category="time",
        knowledge_query="刹车响应时间",
    )
    no_unit = Candidate(
        id="hold_90",
        candidate_type="numeric",
        value="90",
        explanation="ACC 最长保持 90 秒",
        source_type=SourceType.TAVILY,
        source_reference="https://example.com/hold",
    )
    activation_speed = Candidate(
        id="speed_15",
        candidate_type="numeric",
        value="15 km/h",
        explanation="ACC 在该速度以上启用",
        source_type=SourceType.TAVILY,
        source_reference="https://example.com/speed",
    )

    assert workflow._candidate_semantic_problem(ambiguity, no_unit) is not None
    assert workflow._candidate_semantic_problem(ambiguity, activation_speed) is not None


def test_rule_review_removes_signal_names_from_parameters() -> None:
    workflow = build_workflow(FakeChat([]), [])
    ambiguity = Ambiguity(
        id="define_braking_trigger",
        issue_type="vagueness",
        description="必要时刹车的触发条件不明确",
        question="刹车触发条件是什么？",
        category="threshold",
        knowledge_query="刹车触发条件",
    )
    candidate = Candidate(
        id="distance_trigger",
        candidate_type="parameterized",
        value="front_vehicle_distance < d_brake && front_vehicle_closing_speed > 0",
        explanation="距离不足且正在接近时触发",
        parameters=["front_vehicle_distance", "front_vehicle_closing_speed", "d_brake"],
        source_type=SourceType.LLM_INFERENCE,
        source_reference="LLM 工程推断",
    )

    accepted, rejected = workflow._rule_review_candidates(ambiguity, [candidate])

    assert not rejected
    assert accepted[0].parameters == ["d_brake"]


def test_llm_review_can_normalize_response_deadline_candidate() -> None:
    ambiguity = Ambiguity(
        id="define_braking_response_deadline",
        issue_type="vagueness",
        description="及时刹车缺少响应时限",
        question="多长时间内刹车？",
        category="time",
        knowledge_query="刹车响应时间",
    )
    original = Candidate(
        id="response_limit",
        candidate_type="parameterized",
        value="braking_response_time <= max_response_time",
        explanation="响应时间不超过参数上界",
        parameters=["braking_response_time", "max_response_time"],
        source_type=SourceType.LLM_INFERENCE,
        source_reference="LLM 工程推断",
    )
    normalized = Candidate(
        id="response_limit",
        candidate_type="parameterized",
        value="eventually[0,max_response_time](brake_active == 1)",
        explanation="在参数化时限内激活制动请求",
        parameters=["max_response_time"],
        source_type=SourceType.LLM_INFERENCE,
        source_reference="LLM 工程推断",
    )
    chat = FakeChat(
        [
            CandidateReviewSet(
                reviews=[
                    CandidateReview(
                        candidate_id="response_limit",
                        accepted=True,
                        reason="语义正确，规范化为 STL 响应片段",
                        normalized_candidate=normalized,
                    )
                ]
            )
        ]
    )
    workflow = build_workflow(chat, [])

    accepted, rejected = workflow._review_candidates(
        "必要时及时刹车",
        vehicle_context(),
        ambiguity,
        [original],
        "信号名=brake_active",
    )

    assert not rejected
    assert accepted[0].value == "eventually[0,max_response_time](brake_active == 1)"


def test_rejected_candidates_are_regenerated_and_reviewed_again() -> None:
    ambiguity = Ambiguity(
        id="define_safe_distance",
        issue_type="vagueness",
        description="安全距离没有明确的定义",
        question="安全距离是多少？",
        category="threshold",
        knowledge_query="安全距离",
    )
    initial = [
        Candidate(
            id="distance_3",
            candidate_type="numeric",
            value="3 m",
            explanation="固定安全距离",
            source_type=SourceType.LLM_INFERENCE,
            source_reference="LLM 工程推断",
        ),
        Candidate(
            id="distance_4",
            candidate_type="numeric",
            value="4 m",
            explanation="固定安全距离",
            source_type=SourceType.LLM_INFERENCE,
            source_reference="LLM 工程推断",
        ),
    ]
    regenerated = [
        Candidate(
            id="distance_5",
            candidate_type="numeric",
            value="5 m",
            explanation="固定安全距离",
            source_type=SourceType.LLM_INFERENCE,
            source_reference="LLM 工程推断",
        ),
        Candidate(
            id="distance_6",
            candidate_type="numeric",
            value="6 m",
            explanation="固定安全距离",
            source_type=SourceType.LLM_INFERENCE,
            source_reference="LLM 工程推断",
        ),
    ]
    chat = FakeChat(
        [
            CandidateReviewSet(
                reviews=[
                    CandidateReview(
                        candidate_id=item.id,
                        accepted=False,
                        reason="证据不足",
                    )
                    for item in initial
                ]
            ),
            CandidateSet(candidates=regenerated),
            CandidateReviewSet(
                reviews=[
                    CandidateReview(
                        candidate_id=item.id,
                        accepted=True,
                        reason="直接回答安全距离问题",
                    )
                    for item in regenerated
                ]
            ),
        ]
    )
    workflow = build_workflow(chat, [])

    result = workflow._review_and_regenerate_candidates(
        "自车应与前车保持安全距离",
        vehicle_context(),
        ambiguity,
        initial,
        "信号名=front_vehicle_distance；单位 m",
        ["signals_kb.txt#Autonomous_Driving/ACC/front_vehicle_distance"],
    )

    assert [item.value for item in result] == ["5 m", "6 m"]
    assert chat.calls == 3


def test_semantic_plan_is_rebuilt_after_dimension_error() -> None:
    clarification = Clarification(
        ambiguity_id="low_speed",
        category="threshold",
        question="低速是多少？",
        answer="5 km/h",
        semantic_role="predicate",
        source_type=SourceType.USER_INPUT,
        source_reference="用户输入",
    )
    speed = NumericExpression(kind="signal", name="ego_speed")
    invalid_constant = NumericExpression(
        kind="constant",
        value=5,
        unit="m",
        source_clarification_id="low_speed",
    )
    valid_constant = invalid_constant.model_copy(update={"unit": "km/h"})
    invalid = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["low_speed"],
                condition=PredicateExpression(
                    kind="comparison",
                    left=speed,
                    operator="<=",
                    right=invalid_constant,
                ),
            )
        ]
    )
    valid = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["low_speed"],
                condition=PredicateExpression(
                    kind="comparison",
                    left=speed,
                    operator="<=",
                    right=valid_constant,
                ),
            )
        ]
    )
    chat = FakeChat([invalid, valid])
    workflow = build_workflow(chat, [])
    context = DomainContext(
        domain="自动驾驶",
        scene="泊车",
        subject="自车",
        knowledge_scenes=["Parking"],
    )

    result = workflow._generate_compiled_result(
        "泊车过程中保持低速", context, [clarification]
    )

    assert result.formula == "always(ego_speed <= 5)"
    assert chat.calls == 2


def test_full_distance_trigger_and_one_second_response_are_compiled() -> None:
    safe_distance = Clarification(
        ambiguity_id="safe_distance",
        category="threshold",
        question="安全距离是多少？",
        answer="安全距离为自车时速数值的两倍距离",
        semantic_role="predicate",
        source_type=SourceType.USER_INPUT,
        source_reference="用户输入",
    )
    trigger = Clarification(
        ambiguity_id="braking_trigger",
        category="threshold",
        question="何时需要刹车？",
        answer="front_vehicle_distance <= d_brake && front_vehicle_closing_speed > 0",
        supporting_text="d_brake 单位为 m",
        semantic_role="response_trigger",
        source_type=SourceType.LLM_INFERENCE,
        source_reference="LLM 工程推断",
    )
    deadline = Clarification(
        ambiguity_id="braking_deadline",
        category="time",
        question="多长时间内刹车？",
        answer="约 1 秒",
        semantic_role="response_deadline",
        source_type=SourceType.TAVILY,
        source_reference="https://example.com",
    )
    distance_ratio = NumericExpression(
        kind="constant",
        value=2,
        unit="m/(km/h)",
        source_clarification_id="safe_distance",
    )
    distance_rule = PredicateExpression(
        kind="comparison",
        left=NumericExpression(kind="signal", name="front_vehicle_distance"),
        operator=">=",
        right=NumericExpression(
            kind="multiply",
            left=distance_ratio,
            right=NumericExpression(kind="signal", name="ego_speed"),
        ),
    )
    trigger_rule = PredicateExpression(
        kind="and",
        operands=[
            PredicateExpression(
                kind="comparison",
                left=NumericExpression(kind="signal", name="front_vehicle_distance"),
                operator="<=",
                right=NumericExpression(
                    kind="parameter",
                    name="d_brake",
                    unit="m",
                    source_clarification_id="braking_trigger",
                ),
            ),
            PredicateExpression(
                kind="comparison",
                left=NumericExpression(
                    kind="signal", name="front_vehicle_closing_speed"
                ),
                operator=">",
                right=NumericExpression(
                    kind="constant",
                    value=0,
                    unit="km/h",
                    source_clarification_id="braking_trigger",
                ),
            ),
        ],
    )
    brake_target = PredicateExpression(
        kind="comparison",
        left=NumericExpression(kind="signal", name="brake_active"),
        operator="==",
        right=NumericExpression(kind="constant", value=1, unit="boolean"),
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["safe_distance"],
                condition=distance_rule,
            ),
            SemanticRequirement(
                kind="response",
                clarification_ids=["braking_trigger", "braking_deadline"],
                trigger=trigger_rule,
                target=brake_target,
                deadline=NumericExpression(
                    kind="constant",
                    value=1,
                    unit="s",
                    source_clarification_id="braking_deadline",
                ),
            ),
        ]
    )
    chat = FakeChat([plan])
    workflow = build_workflow(chat, [])
    context = DomainContext(
        domain="自动驾驶",
        scene="ACC 跟车制动",
        subject="自车",
        knowledge_scenes=["ACC"],
    )

    result = workflow._generate_compiled_result(
        "自车应与前车保持安全距离，并在必要的时候及时刹车",
        context,
        [safe_distance, trigger, deadline],
    )

    assert "front_vehicle_distance >= (2 * ego_speed)" in result.formula
    assert "eventually[0,1](brake_active == 1)" in result.formula
    assert "always[0,1]" not in result.formula


def test_workflow_normalizes_candidate_divide_by_3_6_before_provenance_check() -> None:
    clarification = Clarification(
        ambiguity_id="safe_distance",
        category="threshold",
        question="安全距离是多少？",
        answer="front_vehicle_distance >= ego_speed / 3.6 * T",
        supporting_text="T 为设定的安全时间头距阈值，单位为 s",
        semantic_role="predicate",
        source_type=SourceType.LLM_INFERENCE,
        source_reference="LLM 工程推断",
    )
    plan = SemanticPlan(
        requirements=[
            SemanticRequirement(
                kind="invariant",
                clarification_ids=["safe_distance"],
                condition=PredicateExpression(
                    kind="comparison",
                    left=NumericExpression(
                        kind="signal", name="front_vehicle_distance"
                    ),
                    operator=">=",
                    right=NumericExpression(
                        kind="multiply",
                        left=NumericExpression(
                            kind="divide",
                            left=NumericExpression(kind="signal", name="ego_speed"),
                            right=NumericExpression(
                                kind="constant",
                                value=3.6,
                                unit="1",
                                source_clarification_id="original",
                            ),
                        ),
                        right=NumericExpression(
                            kind="parameter",
                            name="T",
                            unit="s",
                            source_clarification_id="safe_distance",
                        ),
                    ),
                ),
            )
        ]
    )
    workflow = build_workflow(FakeChat([plan]), [])
    context = DomainContext(
        domain="自动驾驶",
        scene="ACC",
        subject="自车",
        knowledge_scenes=["ACC"],
    )

    result = workflow._generate_compiled_result(
        "自车应与前车保持安全距离", context, [clarification]
    )

    assert "ego_speed * 0.277778" in result.formula
    assert "3.6" not in result.formula
