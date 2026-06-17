from __future__ import annotations

import json

from langgraph.types import Command

from nl2stl_app.config import RuntimeCatalog, Settings
from nl2stl_app.graph import (
    _session_output_dir,
    _simple_reference_candidates,
    _stl_semantics,
    build_graph,
    initial_state,
)
from nl2stl_app.knowledge import KnowledgeBase


def predicate(relation="<", value=5, signal="ego_speed"):
    return {
        "nodeType": "predicate",
        "left": {"exprType": "signal", "name": signal},
        "relation": relation,
        "right": {"exprType": "constant", "value": value},
    }


def always(operand):
    return {
        "nodeType": "temporal",
        "operator": "always",
        "interval": {
            "lower": 0,
            "upper": "inf",
            "lowerInclusive": True,
            "upperInclusive": False,
        },
        "operands": [operand],
    }


def ambiguous_semantics():
    return {
        "revision": 0,
        "summary": "泊车期间保持低速，但低速阈值不明确",
        "is_clear": False,
        "items": [
            {
                "id": "duration",
                "nl_fragment": "整个泊车过程中始终",
                "kind": "temporal",
                "value": "全程始终成立",
                "stl_fragment": "always",
                "status": "resolved",
                "source": "original_nl",
            },
            {
                "id": "speed_signal",
                "nl_fragment": "自车速度",
                "kind": "signal",
                "value": "ego_speed",
                "stl_fragment": "ego_speed",
                "status": "resolved",
                "source": "original_nl",
            },
            {
                "id": "low_speed",
                "nl_fragment": "保持低速",
                "kind": "predicate",
                "value": "阈值和边界待确认",
                "stl_fragment": "ego_speed ? threshold",
                "status": "pending",
                "source": "original_nl",
            },
        ],
        "ambiguities": [
            {
                "id": "low_speed_threshold",
                "nl_fragment": "保持低速",
                "category": "threshold",
                "description": "低速缺少量化阈值和比较边界",
                "question": "低速采用什么数值或公式？",
            }
        ],
        "mappings": [
            {"nl_fragment": "整个泊车过程中始终", "stl_fragment": "always", "status": "resolved"},
            {"nl_fragment": "保持低速", "stl_fragment": "ego_speed ? threshold", "status": "pending"},
        ],
    }


def clear_semantics(relation="<", value=5, guarded=False):
    condition = f"ego_speed {relation} {value}"
    items = [
        {
            "id": "duration",
            "nl_fragment": "整个泊车过程中始终",
            "kind": "temporal",
            "value": "全程始终成立",
            "stl_fragment": "always",
            "status": "resolved",
            "source": "original_nl",
        },
        {
            "id": "speed_signal",
            "nl_fragment": "自车速度",
            "kind": "signal",
            "value": "ego_speed",
            "stl_fragment": "ego_speed",
            "status": "resolved",
            "source": "original_nl",
        },
        {
            "id": "low_speed",
            "nl_fragment": "保持低速",
            "kind": "predicate",
            "value": condition,
            "stl_fragment": condition,
            "status": "resolved",
            "source": "user" if value != 5 or relation != "<" else "original_nl",
        },
    ]
    mappings = [
        {"nl_fragment": "整个泊车过程中始终", "stl_fragment": "always", "status": "resolved"},
        {"nl_fragment": "保持低速", "stl_fragment": condition, "status": "resolved"},
    ]
    summary = f"始终满足 {condition}"
    if guarded:
        items.append(
            {
                "id": "parking_scope",
                "nl_fragment": "仅在泊车模式激活时",
                "kind": "scope",
                "value": "parking_mode == 1",
                "stl_fragment": "parking_mode == 1",
                "status": "resolved",
                "source": "user",
            }
        )
        mappings.append(
            {"nl_fragment": "仅在泊车模式激活时", "stl_fragment": "parking_mode == 1", "status": "resolved"}
        )
        summary = f"始终满足 parking_mode == 1 -> {condition}"
    return {
        "revision": 0,
        "summary": summary,
        "is_clear": True,
        "items": items,
        "ambiguities": [],
        "mappings": mappings,
    }


def unbound_safe_distance_semantics():
    return {
        "revision": 0,
        "summary": "ACC 激活期间始终保持安全距离",
        "is_clear": True,
        "items": [
            {
                "id": "acc_scope",
                "nl_fragment": "ACC 跟车过程中",
                "kind": "scope",
                "value": "acc_active == 1",
                "stl_fragment": "acc_active == 1",
                "status": "resolved",
                "source": "original_nl",
            },
            {
                "id": "safe_distance",
                "nl_fragment": "保持安全距离",
                "kind": "predicate",
                "value": "前车距离大于等于安全距离阈值",
                "stl_fragment": "front_vehicle_distance >= safe_distance_threshold",
                "status": "resolved",
                "source": "original_nl",
            },
        ],
        "ambiguities": [],
        "mappings": [
            {
                "nl_fragment": "ACC 跟车过程中",
                "stl_fragment": "acc_active == 1",
                "status": "resolved",
            },
            {
                "nl_fragment": "保持安全距离",
                "stl_fragment": "front_vehicle_distance >= safe_distance_threshold",
                "status": "resolved",
            },
        ],
    }


class FakeLLM:
    def __init__(
        self,
        ambiguous: bool,
        review_only_one: bool = False,
        invalid_revision_sources: bool = False,
        invalid_revision_status: bool = False,
        unbound_parameter: bool = False,
    ) -> None:
        self.ambiguous = ambiguous
        self.review_only_one = review_only_one
        self.invalid_revision_sources = invalid_revision_sources
        self.invalid_revision_status = invalid_revision_status
        self.unbound_parameter = unbound_parameter
        self.calls = []

    def invoke(self, prompt_id, format_id=None, output_schema=None, **values):
        self.calls.append(prompt_id)
        if prompt_id == "select_signals":
            return {
                "domain": "Autonomous_Driving",
                "scenes": ["Parking"],
                "signals": ["ego_speed", "parking_mode"],
                "missing_concepts": [],
                "reason": "泊车速度与泊车状态",
            }
        if prompt_id == "initialize_global_semantics":
            if self.unbound_parameter:
                return unbound_safe_distance_semantics()
            return ambiguous_semantics() if self.ambiguous else clear_semantics()
        if prompt_id == "review_global_semantics":
            semantics = json.loads(values["global_semantics"])
            semantics["is_clear"] = not semantics["ambiguities"]
            return semantics
        if prompt_id == "generate_candidates_local":
            if self.unbound_parameter:
                return {
                    "candidates": [
                        {
                            "id": "two_seconds",
                            "value": "front_vehicle_distance >= ego_speed / 3.6 * 2",
                            "explanation": "采用2秒时距",
                            "source_type": "llm_generated",
                            "source_reference": "LLM 生成，待用户确认",
                            "canonical": "front_vehicle_distance>=ego_speed/3.6*2",
                        },
                        {
                            "id": "half_speed",
                            "value": "front_vehicle_distance >= ego_speed / 2",
                            "explanation": "采用车速除以2的米数",
                            "source_type": "llm_generated",
                            "source_reference": "LLM 生成，待用户确认",
                            "canonical": "front_vehicle_distance>=ego_speed/2",
                        },
                    ],
                    "insufficient_reason": "",
                }
            return {
                "candidates": [
                    {"id": "five", "value": "ego_speed < 5 km/h", "explanation": "严格低于 5 km/h", "source_type": "llm_generated", "source_reference": "LLM 生成，待用户确认", "canonical": "ego_speed<5km/h"},
                    {"id": "ten", "value": "ego_speed < 10 km/h", "explanation": "严格低于 10 km/h", "source_type": "llm_generated", "source_reference": "LLM 生成，待用户确认", "canonical": "ego_speed<10km/h"},
                ],
                "insufficient_reason": "",
            }
        if prompt_id == "review_candidates":
            accepted = ["five"] if self.review_only_one else ["five", "ten"]
            return {"accepted_ids": accepted, "rejections": []}
        if prompt_id == "revise_global_semantics":
            current = json.loads(values["global_semantics"])
            user_input = values["user_input"]
            if self.unbound_parameter:
                selected = json.loads(values["selected_candidate"])
                formula = (
                    selected.get("value")
                    if selected
                    else "front_vehicle_distance >= ego_speed * 2"
                )
                revised = {
                    "revision": 0,
                    "summary": f"ACC 激活期间始终满足 {formula}",
                    "is_clear": True,
                    "items": [
                        {
                            "id": "acc_scope",
                            "nl_fragment": "ACC 跟车过程中",
                            "kind": "scope",
                            "value": "acc_active == 1",
                            "stl_fragment": "acc_active == 1",
                            "status": "resolved",
                            "source": "original_nl",
                        },
                        {
                            "id": "safe_distance",
                            "nl_fragment": "安全距离",
                            "kind": "definition",
                            "value": formula,
                            "status": "resolved",
                            "source": "user_choice",
                            "unit": "m",
                        },
                    ],
                    "ambiguities": [],
                    "mappings": [
                        {
                            "nl_fragment": "ACC 跟车过程中",
                            "stl_fragment": "acc_active == 1",
                            "status": "resolved",
                        },
                        {
                            "nl_fragment": "安全距离",
                            "stl_fragment": formula,
                            "status": "resolved",
                        },
                    ],
                }
                return {
                    "applicable": True,
                    "revised_semantics": revised,
                    "change_summary": "按用户输入量化安全距离",
                    "reason": "用户给出了可计算公式",
                    "needs_follow_up": False,
                    "follow_up_question": None,
                }
            if user_input == "3":
                return {
                    "applicable": False,
                    "revised_semantics": current,
                    "change_summary": "无",
                    "reason": "数值 3 缺少比较边界和单位",
                    "needs_follow_up": True,
                    "follow_up_question": "请补充比较符和单位",
                }
            guarded = "parking_mode" in user_input
            relation = "<=" if "<=" in user_input else "<"
            value = 3 if "3" in user_input else 5
            revised = clear_semantics(relation, value, guarded)
            if self.invalid_revision_sources:
                revised["items"][0]["source"] = "user_choice_amb_1_opt_1"
                revised["items"][-1]["source"] = "user_choice"
            if self.invalid_revision_status:
                revised["items"][0]["status"] = "confirmed"
                revised["mappings"][0]["status"] = "confirmed"
            return {
                "applicable": True,
                "revised_semantics": revised,
                "change_summary": "按用户输入更新完整语义",
                "reason": "输入与当前需求相关且信息完整",
                "needs_follow_up": False,
                "follow_up_question": None,
            }
        if prompt_id == "validate_semantic_revision":
            return {"valid": True, "reason": "修订一致", "follow_up_question": None}
        if prompt_id == "generate_ast":
            semantics = json.loads(values["global_semantics"])
            summary = semantics["summary"]
            if self.unbound_parameter:
                if "/ 3.6 * 2" in summary:
                    right = {
                        "exprType": "binary",
                        "operator": "multiply",
                        "left": {
                            "exprType": "binary",
                            "operator": "divide",
                            "left": {"exprType": "signal", "name": "ego_speed"},
                            "right": {"exprType": "constant", "value": 3.6},
                        },
                        "right": {"exprType": "constant", "value": 2},
                    }
                else:
                    right = {
                        "exprType": "binary",
                        "operator": "multiply",
                        "left": {"exprType": "signal", "name": "ego_speed"},
                        "right": {"exprType": "constant", "value": 2},
                    }
                return always(
                    {
                        "nodeType": "boolean",
                        "operator": "implies",
                        "operands": [
                            predicate("==", 1, "acc_active"),
                            {
                                "nodeType": "predicate",
                                "left": {
                                    "exprType": "signal",
                                    "name": "front_vehicle_distance",
                                },
                                "relation": ">=",
                                "right": right,
                            },
                        ],
                    }
                )
            relation = "<=" if "<=" in summary else "<"
            value = 3 if "3" in summary else 5
            speed = predicate(relation, value)
            if "parking_mode" in summary:
                body = {
                    "nodeType": "boolean",
                    "operator": "implies",
                    "operands": [predicate("==", 1, "parking_mode"), speed],
                }
                return always(body)
            return always(speed)
        if prompt_id == "semantic_review":
            return {"valid": True, "errors": [], "reason": "一致"}
        raise AssertionError(f"unexpected prompt: {prompt_id}")


class FakeTavily:
    def search(self, query):
        return []


def settings():
    return Settings(
        api_key="test",
        base_url="https://example.invalid",
        tavily_api_key=None,
        model="test",
        timeout_seconds=1,
        max_llm_attempts=2,
        max_ast_repairs=2,
    )


def test_clear_requirement_runs_to_verified_stl():
    llm = FakeLLM(False)
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), llm, FakeTavily())
    state = initial_state("整个泊车过程中，车辆速度应始终低于 5 千米每小时", "clear-test")
    output = graph.invoke(state, config={"configurable": {"thread_id": "clear-test"}})
    assert output["status"] == "complete"
    assert output["result"]["stl"] == "always (ego_speed < 5)"
    assert output["result"]["ast_path"] == "tmp/single/clear-test/ast.json"
    assert output["result"]["stl_semantics"].startswith("清晰化需求：")
    assert output["result"]["elapsed_seconds"] >= 0
    assert "select_signals" not in llm.calls
    assert "review_global_semantics" not in llm.calls
    assert "semantic_review" not in llm.calls


def test_batch_output_mode_uses_run_and_case_path():
    state = initial_state(
        "速度始终低于 5 km/h",
        session_id="case_001",
        output_mode="batch",
        output_run_id="run_001",
    )

    assert str(_session_output_dir(state)).endswith("tmp/batch/run_001/case_001")


def test_aeb_requirement_uses_local_signal_routing():
    selection = KnowledgeBase().infer_selection(
        "At all times, if the time to collision has just dropped below 2.5 seconds, "
        "collision warning and braking request shall be active."
    )

    assert selection == {
        "domain": "Autonomous_Driving",
        "scenes": ["AEB"],
        "signals": ["brake_active", "collision_warning", "ttc"],
        "missing_concepts": [],
        "reason": "文本中的场景和信号可由本地索引唯一确定",
    }


def test_simple_time_ambiguity_uses_reference_values_without_search_formulas():
    candidates = _simple_reference_candidates(
        {
            "id": "few_seconds",
            "nl_fragment": "for the next few seconds",
            "category": "time",
            "description": "next few seconds 未明确具体时间长度",
            "question": "next few seconds 具体是几秒？",
        }
    )

    assert [item["value"] for item in candidates] == ["2 s", "3 s", "5 s"]
    assert all(item["source_reference"] == "本地参考值，需用户确认" for item in candidates)


def test_simple_meter_threshold_uses_reference_values_without_search_formulas():
    candidates = _simple_reference_candidates(
        {
            "id": "some_meters",
            "nl_fragment": "some meters",
            "category": "threshold",
            "description": "some meters 未给出具体数值",
            "question": "some meters 的具体数值是多少？",
        }
    )

    assert [item["value"] for item in candidates] == ["5 m", "10 m"]


def test_stl_semantics_is_clear_natural_language_not_process_summary():
    ast = always(
        {
            "nodeType": "predicate",
            "left": {"exprType": "signal", "name": "front_obstacle_distance"},
            "relation": ">",
            "right": {"exprType": "constant", "value": 10},
        }
    )
    ast["interval"]["upper"] = 2
    state = {
        "original_text": "for the next few seconds, the distance shall remain greater than some meters.",
        "ast": ast,
        "global_semantics": {
            "summary": "建立全局语义状态。这个文本不应出现在最终语义描述里。"
        },
    }

    assert _stl_semantics(state) == (
        "for the next 2 seconds, the distance shall remain greater than 10 meters."
    )


def test_stl_semantics_replaces_clarified_low_speed_threshold():
    ast = always(predicate("<=", 5))
    ast["interval"]["upper"] = 20
    state = {
        "original_text": (
            "For the next few seconds, the ego vehicle speed shall remain low speed"
        ),
        "ast": ast,
        "global_semantics": {
            "items": [
                {
                    "nl_fragment": "low speed",
                    "value": "ego_speed <= 5",
                    "stl_fragment": "ego_speed <= 5",
                    "status": "resolved",
                }
            ],
            "mappings": [],
        },
    }

    assert _stl_semantics(state) == (
        "For the next 20 seconds, the ego vehicle speed shall remain at or below 5 km/h"
    )


def test_chinese_stl_semantics_keeps_original_language():
    ast = always(
        {
            "nodeType": "predicate",
            "left": {"exprType": "signal", "name": "front_obstacle_distance"},
            "relation": ">",
            "right": {"exprType": "constant", "value": 10},
        }
    )
    ast["interval"]["upper"] = 2
    state = {
        "original_text": "接下来几秒，前方障碍物距离应始终大于若干米。",
        "ast": ast,
        "global_semantics": {
            "items": [{"nl_fragment": "meters", "value": "m"}],
            "mappings": [],
        },
    }

    assert _stl_semantics(state) == "接下来 2 秒，前方障碍物距离应始终大于10米。"


def test_unbound_safe_distance_parameter_forces_clarification():
    llm = FakeLLM(False, unbound_parameter=True)
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), llm, FakeTavily())
    config = {"configurable": {"thread_id": "safe-distance-test"}}

    interrupted = graph.invoke(
        initial_state(
            "ACC 跟车过程中，车辆与前车应始终保持安全距离",
            "safe-distance-test",
        ),
        config=config,
    )

    payload = interrupted["__interrupt__"][0].value
    assert payload["global_semantics"]["is_clear"] is False
    assert payload["ambiguity"]["id"] == "unbound_parameter_safe_distance_threshold"
    assert payload["ambiguity"]["category"] == "threshold"
    assert "generate_ast" not in llm.calls


def test_custom_safe_distance_formula_is_accepted_without_llm_veto():
    llm = FakeLLM(False, unbound_parameter=True)
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), llm, FakeTavily())
    config = {"configurable": {"thread_id": "custom-safe-distance-test"}}
    graph.invoke(
        initial_state(
            "ACC 跟车过程中，车辆与前车应始终保持安全距离",
            "custom-safe-distance-test",
        ),
        config=config,
    )

    output = graph.invoke(Command(resume="安全距离采用两倍时速距离"), config=config)

    assert output["status"] == "complete"
    assert output["result"]["stl"] == (
        "always (acc_active == 1 -> front_vehicle_distance >= ego_speed * 2)"
    )
    assert "validate_semantic_revision" not in llm.calls
    assert "review_global_semantics" not in llm.calls


def test_selected_safe_distance_candidate_is_applied_without_reinterpretation():
    llm = FakeLLM(False, unbound_parameter=True)
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), llm, FakeTavily())
    config = {"configurable": {"thread_id": "selected-safe-distance-test"}}
    graph.invoke(
        initial_state(
            "ACC 跟车过程中，车辆与前车应始终保持安全距离",
            "selected-safe-distance-test",
        ),
        config=config,
    )

    output = graph.invoke(Command(resume="A"), config=config)

    assert output["status"] == "complete"
    assert output["result"]["stl"] == (
        "always (acc_active == 1 -> "
        "front_vehicle_distance >= ego_speed / 3.6 * 2)"
    )
    assert "validate_semantic_revision" not in llm.calls
    assert "review_global_semantics" not in llm.calls


def test_ambiguous_requirement_interrupts_and_updates_global_semantics():
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), FakeLLM(True), FakeTavily())
    config = {"configurable": {"thread_id": "ambiguous-test"}}
    interrupted = graph.invoke(initial_state("泊车期间始终保持低速", "ambiguous-test"), config=config)
    payload = interrupted["__interrupt__"][0].value
    assert payload["global_semantics"]["is_clear"] is False
    assert len(payload["candidates"]) == 2

    output = graph.invoke(Command(resume="A"), config=config)
    assert output["status"] == "complete"
    assert output["result"]["global_semantics"]["revision"] == 1
    assert output["semantic_history"][0]["semantics"]["is_clear"] is False


def test_incomplete_custom_answer_is_rejected_then_formula_is_accepted():
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), FakeLLM(True), FakeTavily())
    config = {"configurable": {"thread_id": "custom-test"}}
    graph.invoke(initial_state("泊车期间始终保持低速", "custom-test"), config=config)

    interrupted_again = graph.invoke(Command(resume="3"), config=config)
    payload = interrupted_again["__interrupt__"][0].value
    assert "比较边界" in payload["feedback"]

    output = graph.invoke(Command(resume="ego_speed <= 3 km/h"), config=config)
    assert output["status"] == "complete"
    assert output["result"]["stl"] == "always (ego_speed <= 3)"


def test_custom_answer_can_overturn_other_parts_of_global_semantics():
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), FakeLLM(True), FakeTavily())
    config = {"configurable": {"thread_id": "global-revision-test"}}
    graph.invoke(initial_state("泊车期间始终保持低速", "global-revision-test"), config=config)

    output = graph.invoke(
        Command(resume="改为仅在 parking_mode == 1 时，ego_speed < 3 km/h"),
        config=config,
    )
    assert output["status"] == "complete"
    assert output["result"]["stl"] == "always (parking_mode == 1 -> ego_speed < 3)"
    assert any(item["id"] == "parking_scope" for item in output["result"]["global_semantics"]["items"])


def test_llm_candidate_review_cannot_veto_rule_valid_candidates():
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), FakeLLM(True, review_only_one=True), FakeTavily())
    config = {"configurable": {"thread_id": "review-fallback-test"}}
    interrupted = graph.invoke(initial_state("泊车期间始终保持低速", "review-fallback-test"), config=config)
    assert len(interrupted["__interrupt__"][0].value["candidates"]) == 2


def test_confirmed_candidate_normalizes_model_invented_source_labels():
    llm = FakeLLM(True, invalid_revision_sources=True)
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), llm, FakeTavily())
    config = {"configurable": {"thread_id": "source-normalization-test"}}
    graph.invoke(initial_state("泊车期间始终保持低速", "source-normalization-test"), config=config)

    output = graph.invoke(Command(resume="A"), config=config)

    assert output["status"] == "complete"
    assert all(
        item["source"] in {"original_nl", "user", "knowledge_base", "search", "llm_inference"}
        for item in output["result"]["global_semantics"]["items"]
    )
    assert "validate_semantic_revision" not in llm.calls


def test_confirmed_status_drift_is_normalized_in_revision():
    llm = FakeLLM(True, invalid_revision_status=True)
    graph = build_graph(settings(), RuntimeCatalog(), KnowledgeBase(), llm, FakeTavily())
    config = {"configurable": {"thread_id": "status-normalization-test"}}
    graph.invoke(initial_state("泊车期间始终保持低速", "status-normalization-test"), config=config)

    output = graph.invoke(Command(resume="A"), config=config)

    assert output["status"] == "complete"
    assert output["result"]["global_semantics"]["items"][0]["status"] == "resolved"
    assert output["result"]["global_semantics"]["mappings"][0]["status"] == "resolved"


def test_progress_callback_reports_real_execution_steps():
    steps = []
    graph = build_graph(
        settings(), RuntimeCatalog(), KnowledgeBase(), FakeLLM(False), FakeTavily(), progress=steps.append
    )
    graph.invoke(initial_state("速度始终低于 5 km/h", "progress-test"), config={"configurable": {"thread_id": "progress-test"}})
    assert any("选择领域" in step for step in steps)
    assert any("生成 AST" in step for step in steps)
    assert any("validate_ast.py" in step for step in steps)
