from __future__ import annotations

import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from .schemas import Ambiguity, Candidate, GraphState, SourceType


def build_state_graph():
    """A network-free LangGraph that selects the next unresolved ambiguity."""

    def select_next(state: GraphState) -> dict:
        ambiguities = state.get("ambiguities", [])
        return {"current_ambiguity": ambiguities[0] if ambiguities else None}

    builder = StateGraph(GraphState)
    builder.add_node("select_next", select_next)
    builder.add_edge(START, "select_next")
    builder.add_edge("select_next", END)
    return builder.compile()


def advance_state(state: GraphState) -> GraphState:
    return build_state_graph().invoke(state)


def remove_current_ambiguity(state: GraphState) -> GraphState:
    current = state.get("current_ambiguity") or {}
    current_id = current.get("id")
    current_category = current.get("category")
    updated = dict(state)
    updated["ambiguities"] = [
        item
        for item in state.get("ambiguities", [])
        if item.get("id") != current_id
    ]
    updated["current_ambiguity"] = None
    return advance_state(updated)


def resolve_answer(raw_answer: Any, candidates: list[Candidate]) -> tuple[str, Candidate | None]:
    text = str(raw_answer or "").strip()
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(candidates):
            return candidates[index].value, candidates[index]
    for candidate in candidates:
        if text in {candidate.id, candidate.value}:
            return candidate.value, candidate
    if not text:
        raise ValueError("澄清回答不能为空")
    return text, None


def ensure_required_ambiguities(
    original_text: str,
    model_ambiguities: list[Ambiguity],
    clarifications: list[dict],
) -> list[Ambiguity]:
    resolved_categories = {item.get("category") for item in clarifications}
    pending = [item for item in model_ambiguities if item.category not in resolved_categories]
    if _uses_dynamic_speed_limit(original_text):
        pending = [item for item in pending if item.category != "threshold"]
    categories = {item.category for item in pending}

    def has_issue(*keywords: str) -> bool:
        return any(
            any(keyword in f"{item.description} {item.question}" for keyword in keywords)
            for item in pending
        )

    if "安全距离" in original_text and not has_issue("安全距离", "车头时距"):
        pending.append(
            Ambiguity(
                id="define_safe_distance",
                issue_type="vagueness",
                description="“安全距离”缺少具体数值、计算公式或参数化判定规则",
                question="请选择安全距离的具体数值、计算公式或参数化比较方式。",
                category="threshold",
                knowledge_query="安全跟车距离 时间车头时距 TTC 计算公式 阈值",
            )
        )

    if "必要" in original_text and not has_issue("必要", "触发条件", "刹车时机"):
        pending.append(
            Ambiguity(
                id="define_braking_trigger",
                issue_type="vagueness",
                description="“必要时刹车”缺少可执行的触发条件",
                question="请选择触发刹车的具体条件、公式或参数化谓词。",
                category="threshold",
                knowledge_query="自动驾驶 AEB 刹车触发条件 TTC 距离 闭合速度 阈值",
            )
        )

    if "及时" in original_text and not has_issue("及时", "响应时限", "多长时间"):
        pending.append(
            Ambiguity(
                id="define_braking_response_deadline",
                issue_type="vagueness",
                description="“及时刹车”缺少明确响应时限",
                question="请选择刹车动作必须在多长时间内发生，或使用参数化响应时限。",
                category="time",
                knowledge_query="自动紧急制动 AEB 响应时间 制动介入时限 秒",
            )
        )

    categories = {item.category for item in pending}

    vague_terms = [
        term
        for term in ("低速", "安全", "轻踩", "快速", "接近", "较大", "较小")
        if term in original_text
    ]
    if vague_terms and "threshold" not in resolved_categories | categories:
        term = vague_terms[0]
        pending.append(
            Ambiguity(
                id="quantify_vague_threshold",
                issue_type="vagueness",
                description=f"“{term}”缺少可用于 STL 谓词的量化定义",
                question=f"“{term}”具体采用什么数值阈值或计算规则？",
                category="threshold",
                knowledge_query=f"{term} 数值阈值 标准 工程范围",
            )
        )

    if any(word in original_text for word in ("过程中", "过程期间", "运行期间", "控制期间")):
        if "scope" not in resolved_categories | categories:
            pending.append(
                Ambiguity(
                    id="define_process_scope",
                    issue_type="ambiguity",
                    description="过程范围尚未映射为可观测的启停条件",
                    question="该过程使用哪个状态条件或起止事件界定，还是采用整个监测周期？",
                    category="scope",
                    knowledge_query="场景 mode active completed event process scope",
                )
            )

    if any(word in original_text for word in ("始终", "总是", "最终", "曾经", "过去")):
        if "time" not in resolved_categories | categories:
            pending.append(
                Ambiguity(
                    id="define_temporal_interval",
                    issue_type="vagueness",
                    description="时序要求尚未明确采用无界语义还是有限时间区间",
                    question="该时序算子覆盖整个监测周期，还是限定具体时间区间？",
                    category="time",
                    knowledge_query="always eventually historically time interval bounded unbounded",
                )
            )

    order = {"signal": 0, "threshold": 1, "scope": 2, "time": 3, "operator": 4, "other": 5}
    pending.sort(key=lambda item: order[item.category])
    return pending


def _uses_dynamic_speed_limit(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text)
    return "限速" in normalized and any(
        phrase in normalized
        for phrase in ("不得超过", "不能超过", "不超过", "遵守", "以内", "以下")
    )


def generate_local_candidates(state: GraphState) -> list[Candidate]:
    ambiguity = Ambiguity.model_validate(state["current_ambiguity"])
    source_ids = state.get("local_source_ids", [])
    if ambiguity.category == "time" and ambiguity.id == "define_temporal_interval":
        source = next(
            (item for item in source_ids if item.startswith("stl_operators.md#")),
            "stl_operators.md#1. always",
        )
        return [
            Candidate(
                id="whole_monitoring_period",
                candidate_type="formula",
                value="使用无界时序算子，覆盖整个信号监测周期",
                explanation="例如 always(...) 表示整个监测周期始终成立",
                source_type=SourceType.STL_KNOWLEDGE,
                source_reference=source,
            ),
            Candidate(
                id="bounded_interval",
                candidate_type="parameterized",
                value="使用 always[t_start,t_end](phi)，其中 t_start、t_end 由用户或系统参数提供",
                explanation="保留明确的参数化时间区间，不自动猜测具体秒数",
                parameters=["t_start", "t_end"],
                source_type=SourceType.STL_KNOWLEDGE,
                source_reference=source,
            ),
        ]

    if ambiguity.category != "scope":
        return []

    signal_sources = [
        item
        for item in source_ids
        if item.startswith("signals_kb.txt#") and not item.startswith("stl_operators.md#")
    ]
    text = state["original_text"].lower()
    scenario_modes = {
        "泊车": "_parking_mode",
        "停车": "_parking_mode",
        "parking": "_parking_mode",
        "牵引力": "_tcs_active",
        "traction": "_tcs_active",
        "跟车": "_acc_active",
        "acc": "_acc_active",
        "aeb": "_aeb_active",
        "车道保持": "_lkas_active",
        "变道": "_lane_change_active",
    }
    preferred = [suffix.removeprefix("_") for keyword, suffix in scenario_modes.items() if keyword in text]
    mode_source = next(
        (source for name in preferred for source in signal_sources if source.endswith(f"/{name}")),
        next((source for source in signal_sources if source.endswith("_mode") or "/" in source and source.rsplit("/", 1)[-1].endswith("_mode")), ""),
    )
    event_source = next(
        (source for source in signal_sources if "completed_event" in source), mode_source
    )
    mode = mode_source.rsplit("/", 1)[-1] if mode_source else "相关场景状态信号"
    event = event_source.rsplit("/", 1)[-1] if event_source else "完成事件"
    candidates = [
        Candidate(
            id="active_state_scope",
            candidate_type="formula",
            value=f"在 {mode} == 1 期间",
            explanation="使用场景模式状态界定过程",
            source_type=SourceType.SIGNAL_KNOWLEDGE if mode_source else SourceType.LLM_INFERENCE,
            source_reference=mode_source or "LLM 工程推断",
        ),
        Candidate(
            id="event_scope",
            candidate_type="formula",
            value=f"从 rise({mode}) 到 {event} == 1",
            explanation="使用启动沿和完成事件界定过程",
            source_type=SourceType.SIGNAL_KNOWLEDGE if event_source else SourceType.LLM_INFERENCE,
            source_reference=event_source or "LLM 工程推断",
        ),
        Candidate(
            id="whole_trace_scope",
            candidate_type="formula",
            value="采用整个信号监测周期，不增加过程状态条件",
            explanation="把输入轨迹本身视为目标过程",
            source_type=SourceType.LLM_INFERENCE,
            source_reference="用户可选择的建模约定",
        ),
    ]
    if not mode_source:
        return [candidates[-1]]
    return candidates


def sanitize_candidates(
    candidates: list[Candidate], local_ids: set[str], web_urls: set[str]
) -> list[Candidate]:
    sanitized: list[Candidate] = []
    for index, candidate in enumerate(candidates[:3], start=1):
        source_type = candidate.source_type
        reference = candidate.source_reference.strip().strip("[]")
        if source_type in {SourceType.SIGNAL_KNOWLEDGE, SourceType.STL_KNOWLEDGE}:
            explicit_sources = [
                item.strip() for item in reference.split("；") if item.strip() in local_ids
            ]
            if explicit_sources:
                parent_paths = {
                    source.rsplit("/", 1)[0] for source in explicit_sources if "/" in source
                }
                same_scene_sources = {
                    source
                    for source in local_ids
                    if source.rsplit("/", 1)[0] in parent_paths
                    and re.search(
                        rf"\b{re.escape(source.rsplit('/', 1)[-1])}\b",
                        candidate.value,
                    )
                }
                reference = "；".join(sorted(set(explicit_sources) | same_scene_sources))
            elif reference not in local_ids:
                source_type = SourceType.LLM_INFERENCE
                reference = "LLM 工程推断（本地引用未通过校验）"
        elif source_type == SourceType.TAVILY and reference not in web_urls:
            source_type = SourceType.LLM_INFERENCE
            reference = "LLM 工程推断（Tavily URL 未通过校验）"
        sanitized.append(
            candidate.model_copy(
                update={"id": candidate.id or str(index), "source_type": source_type, "source_reference": reference}
            )
        )
    return sanitized


def executable_candidates(
    ambiguity: Ambiguity,
    candidates: list[Candidate],
    known_signals: set[str],
) -> tuple[list[Candidate], list[str]]:
    accepted: list[Candidate] = []
    rejected: list[str] = []
    for candidate in candidates:
        problem = candidate_quality_problem(ambiguity, candidate, known_signals)
        if problem:
            rejected.append(f"{candidate.id}: {problem}")
        else:
            accepted.append(candidate)
    return accepted, rejected


def candidate_quality_problem(
    ambiguity: Ambiguity,
    candidate: Candidate,
    known_signals: set[str],
) -> str | None:
    value = candidate.value.strip()
    if not value:
        return "候选值为空"
    if "相关场景状态信号" in value or "完成事件" == value.strip():
        return "候选包含未解析的通用占位符"

    if candidate.candidate_type == "numeric":
        if not re.search(r"\d+(?:\.\d+)?", value):
            return "数值候选没有具体数值"
        if ambiguity.category == "threshold" and not re.search(
            r"(?:km/h|m/s|\bms\b|\bs\b|\bm\b|%|无量纲)", value, re.IGNORECASE
        ):
            return "数值候选没有单位"
        return None

    if candidate.candidate_type == "parameterized":
        if not candidate.parameters:
            return "参数化候选没有声明参数"
        missing = [parameter for parameter in candidate.parameters if parameter not in value]
        if missing:
            return f"参数未出现在表达式中：{', '.join(missing)}"
        if ambiguity.category in {"signal", "threshold"} and not re.search(
            r"<=|>=|==|!=|<|>", value
        ):
            return "参数化候选缺少完整比较关系"
        return _unknown_identifier_problem(value, candidate.parameters, known_signals)

    if ambiguity.category in {"signal", "threshold"}:
        required_operator = r"<=|>=|<|>" if ambiguity.category == "threshold" else r"<=|>=|==|!=|<|>|="
        if not re.search(required_operator, value):
            return "公式候选缺少比较或计算关系"
        referenced = {
            signal for signal in known_signals if re.search(rf"\b{re.escape(signal)}\b", value)
        }
        if not referenced:
            return "公式候选没有使用知识库信号"
        placeholder = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*(?:threshold|_min|_max)\b", value)
        if placeholder:
            return "公式含未声明参数，应标为 parameterized 并列出 parameters"
        unknown_problem = _unknown_identifier_problem(value, [], known_signals)
        if unknown_problem:
            return unknown_problem
    return None


def local_evidence_problem(candidate: Candidate, local_context: str) -> str | None:
    if candidate.source_type not in {
        SourceType.SIGNAL_KNOWLEDGE,
        SourceType.STL_KNOWLEDGE,
    }:
        return None
    candidate_numbers = set(re.findall(r"(?<![A-Za-z_])\d+(?:\.\d+)?", candidate.value))
    evidence_numbers = set(re.findall(r"(?<![A-Za-z_])\d+(?:\.\d+)?", local_context))
    unsupported = sorted(candidate_numbers - evidence_numbers)
    if unsupported:
        return f"知识内容未提供数值：{', '.join(unsupported)}"
    return None


def _unknown_identifier_problem(
    value: str, parameters: list[str], known_signals: set[str]
) -> str | None:
    identifiers = set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", value))
    allowed = {
        "true", "false", "and", "or", "not", "rise", "fall", "always",
        "eventually", "until", "km", "h", "m", "s", "pct",
    } | set(parameters)
    signal_like = {item for item in identifiers if "_" in item}
    unknown = sorted(signal_like - known_signals - allowed)
    if unknown:
        return f"使用了知识库中不存在且未声明为参数的标识符：{', '.join(unknown)}"
    return None


def validate_formula(formula: str, declared_signals: list[str], known_signals: set[str]) -> list[str]:
    errors: list[str] = []
    balance = 0
    for char in formula:
        balance += char == "("
        balance -= char == ")"
        if balance < 0:
            errors.append("公式存在未匹配的右括号")
            break
    if balance > 0:
        errors.append("公式存在未闭合的左括号")
    prefixed = sorted(set(re.findall(r"Autonomous_Driving_[A-Za-z0-9_]+", formula)))
    if prefixed:
        errors.append(f"公式不得拼接场景前缀：{', '.join(prefixed)}")
    unknown_declared = sorted(set(declared_signals) - known_signals)
    if unknown_declared:
        errors.append(f"signals_used 包含知识库中不存在的信号：{', '.join(unknown_declared)}")
    missing = sorted(signal for signal in declared_signals if not re.search(rf"\b{re.escape(signal)}\b", formula))
    if missing:
        errors.append(f"signals_used 中的信号未出现在公式：{', '.join(missing)}")
    if not formula.strip():
        errors.append("STL 公式为空")
    return errors
