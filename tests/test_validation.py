from nl2stl_app.knowledge import KnowledgeBase
from nl2stl_app.validation import (
    enforce_semantic_completeness,
    normalize_global_semantics,
    rule_filter_candidates,
    validate_ast_against_semantics,
)


def test_candidate_filter_rejects_narrative_and_multi_branch_choices():
    candidates = [
        {
            "id": "gears",
            "value": "安全距离可通过1~5挡调节，默认3挡",
            "explanation": "档位越高距离越大",
            "source_type": "llm_generated",
            "source_reference": "LLM 生成",
            "canonical": "gears",
        },
        {
            "id": "vehicle_types",
            "value": "小型车安全距离=vehicle_speed_kmh/2，或大型车安全距离=vehicle_speed_kmh-20",
            "explanation": "按车型区分",
            "source_type": "llm_generated",
            "source_reference": "LLM 生成",
            "canonical": "vehicle-types",
        },
    ]

    accepted, rejected = rule_filter_candidates(
        candidates, set(), set(), KnowledgeBase().all_signal_names()
    )

    assert accepted == []
    assert len(rejected) == 2


def test_candidate_filter_accepts_single_formula_with_known_signals():
    candidate = {
        "id": "two_seconds",
        "value": "front_vehicle_distance >= ego_speed / 3.6 * 2",
        "explanation": "采用2秒时距",
        "source_type": "llm_generated",
        "source_reference": "LLM 生成",
        "canonical": "front_vehicle_distance>=ego_speed/3.6*2",
    }

    accepted, rejected = rule_filter_candidates(
        [candidate], set(), set(), KnowledgeBase().all_signal_names()
    )

    assert [item["id"] for item in accepted] == ["two_seconds"]
    assert rejected == []


def test_semantic_normalizer_repairs_common_model_field_drift():
    semantics = {
        "items": [
            {
                "nl_fragment": "安全距离采用两倍时速距离",
                "kind": "definition",
                "value": "front_vehicle_distance >= ego_speed * 2",
                "status": "resolved",
                "source": "user_choice",
                "unit": "m",
            }
        ]
    }

    normalize_global_semantics(semantics)

    assert semantics["items"] == [
        {
            "id": "item_1",
            "nl_fragment": "安全距离采用两倍时速距离",
            "kind": "predicate",
            "value": "front_vehicle_distance >= ego_speed * 2",
            "stl_fragment": "front_vehicle_distance >= ego_speed * 2",
            "status": "resolved",
            "source": "user",
        }
    ]


def test_semantic_normalizer_repairs_confirmed_status_drift():
    semantics = {
        "items": [
            {
                "nl_fragment": "For the next few seconds",
                "kind": "temporal",
                "value": "always[0,20]",
                "stl_fragment": "always[0,20]",
                "status": "confirmed",
                "source": "user",
            }
        ],
        "mappings": [
            {
                "nl_fragment": "For the next few seconds",
                "stl_fragment": "always[0,20]",
                "status": "confirmed",
            }
        ],
    }

    normalize_global_semantics(semantics)

    assert semantics["items"][0]["status"] == "resolved"
    assert semantics["mappings"][0]["status"] == "resolved"


def test_unbound_threshold_parameter_becomes_ambiguity():
    semantics = {
        "revision": 0,
        "summary": "ACC 跟车期间保持安全距离",
        "is_clear": True,
        "items": [
            {
                "id": "safe_distance",
                "nl_fragment": "保持安全距离",
                "kind": "predicate",
                "value": "前车距离大于等于安全距离阈值",
                "stl_fragment": "front_vehicle_distance >= safe_distance_threshold",
                "status": "resolved",
                "source": "original_nl",
            }
        ],
        "ambiguities": [],
        "mappings": [
            {
                "nl_fragment": "保持安全距离",
                "stl_fragment": "front_vehicle_distance >= safe_distance_threshold",
                "status": "resolved",
            }
        ],
    }

    enforce_semantic_completeness(
        semantics, "ACC 跟车过程中，车辆与前车应始终保持安全距离", KnowledgeBase()
    )

    assert semantics["is_clear"] is False
    assert semantics["items"][0]["status"] == "pending"
    assert semantics["mappings"][0]["status"] == "pending"
    assert semantics["ambiguities"][0]["category"] == "threshold"
    assert "safe_distance_threshold" in semantics["ambiguities"][0]["question"]


def test_resolved_parameter_removes_stale_generated_ambiguity():
    semantics = {
        "revision": 1,
        "summary": "安全距离采用2秒时距",
        "is_clear": False,
        "items": [
            {
                "id": "safe_distance",
                "nl_fragment": "保持安全距离",
                "kind": "predicate",
                "value": "front_vehicle_distance >= ego_speed / 3.6 * 2",
                "stl_fragment": "front_vehicle_distance >= ego_speed / 3.6 * 2",
                "status": "resolved",
                "source": "user",
            }
        ],
        "ambiguities": [
            {
                "id": "unbound_parameter_safe_distance_threshold",
                "nl_fragment": "保持安全距离",
                "category": "threshold",
                "description": "旧问题",
                "question": "旧问题",
            }
        ],
        "mappings": [],
    }

    enforce_semantic_completeness(semantics, "保持安全距离", KnowledgeBase())

    assert semantics["ambiguities"] == []
    assert semantics["is_clear"] is True


def test_unit_items_do_not_create_unbound_parameter_ambiguity():
    semantics = {
        "revision": 1,
        "summary": "front_obstacle_distance > 15 m",
        "is_clear": True,
        "items": [
            {
                "id": "distance_signal",
                "nl_fragment": "distance to the front obstacle",
                "kind": "signal",
                "value": "front_obstacle_distance",
                "stl_fragment": "front_obstacle_distance",
                "status": "resolved",
                "source": "original_nl",
            },
            {
                "id": "distance_unit",
                "nl_fragment": "distance unit meters",
                "kind": "unit",
                "value": "meters",
                "stl_fragment": "unit",
                "status": "resolved",
                "source": "original_nl",
            },
            {
                "id": "threshold",
                "nl_fragment": "some meters",
                "kind": "predicate",
                "value": "front_obstacle_distance > 15",
                "stl_fragment": "front_obstacle_distance > 15",
                "status": "resolved",
                "source": "user",
            },
        ],
        "ambiguities": [
            {
                "id": "unbound_parameter_unit",
                "nl_fragment": "distance unit meters",
                "category": "other",
                "description": "stale unit ambiguity",
                "question": "stale unit ambiguity",
            }
        ],
        "mappings": [
            {
                "nl_fragment": "distance to the front obstacle shall remain greater than some meters",
                "stl_fragment": "front_obstacle_distance > 15",
                "status": "resolved",
            }
        ],
    }

    enforce_semantic_completeness(
        semantics,
        "for the next few seconds, the distance to the front obstacle shall remain greater than some meters.",
        KnowledgeBase(),
    )

    assert semantics["ambiguities"] == []
    assert semantics["is_clear"] is True


def test_candidate_filter_rejects_canonical_duplicates():
    candidates = [
        {
            "id": "a",
            "value": "ego_speed < 5 km/h",
            "explanation": "严格低于 5",
            "source_type": "knowledge_base",
            "source_reference": "signals_explain.txt#Autonomous_Driving/Parking/ego_speed",
            "canonical": "ego_speed<5km/h",
        },
        {
            "id": "b",
            "value": "ego_speed <= 5 km/h",
            "explanation": "只改变边界的近重复条件",
            "source_type": "knowledge_base",
            "source_reference": "signals_explain.txt#Autonomous_Driving/Parking/ego_speed",
            "canonical": "ego_speed<=5km/h",
        },
    ]
    accepted, rejected = rule_filter_candidates(
        candidates,
        {"signals_explain.txt#Autonomous_Driving/Parking/ego_speed": "单位 km/h；低速阈值 5 km/h"},
        set(),
    )
    assert [item["id"] for item in accepted] == ["a"]
    assert any("重复" in reason for reason in rejected)


def test_candidate_filter_rejects_threshold_not_present_in_knowledge():
    candidate = {
        "id": "unsupported",
        "value": "ego_speed < 5 km/h",
        "explanation": "知识条目只说明单位，没有给出 5 km/h 阈值",
        "source_type": "knowledge_base",
        "source_reference": "signals_explain.txt#Autonomous_Driving/Parking/ego_speed",
        "canonical": "ego_speed<5km/h",
    }
    accepted, rejected = rule_filter_candidates(
        [candidate],
        {"signals_explain.txt#Autonomous_Driving/Parking/ego_speed": "泊车速度；单位 km/h"},
        set(),
    )
    assert accepted == []
    assert any("数值未被" in reason for reason in rejected)


def test_ast_cannot_introduce_signal_absent_from_global_semantics():
    ast = {
        "nodeType": "boolean",
        "operator": "implies",
        "operands": [
            {
                "nodeType": "predicate",
                "left": {"exprType": "signal", "name": "parking_mode"},
                "relation": "==",
                "right": {"exprType": "constant", "value": 1},
            },
            {
                "nodeType": "predicate",
                "left": {"exprType": "signal", "name": "ego_speed"},
                "relation": "<",
                "right": {"exprType": "constant", "value": 5},
            },
        ],
    }
    semantics = {
        "items": [
            {"status": "resolved", "value": "ego_speed < 5", "stl_fragment": "ego_speed < 5"}
        ],
        "mappings": [],
    }
    errors = validate_ast_against_semantics(ast, semantics, KnowledgeBase())
    assert errors == ["AST 信号 parking_mode 未在当前全局语义中声明"]


def test_ast_cannot_introduce_unresolved_parameter():
    ast = {
        "nodeType": "predicate",
        "left": {"exprType": "signal", "name": "front_vehicle_distance"},
        "relation": ">=",
        "right": {"exprType": "parameter", "name": "safe_distance_threshold"},
    }
    semantics = {
        "items": [
            {
                "status": "resolved",
                "value": "front_vehicle_distance",
                "stl_fragment": "front_vehicle_distance",
            }
        ],
        "mappings": [],
    }

    errors = validate_ast_against_semantics(ast, semantics, KnowledgeBase())

    assert errors == ["AST 参数 safe_distance_threshold 未在已解析的全局语义中声明"]
