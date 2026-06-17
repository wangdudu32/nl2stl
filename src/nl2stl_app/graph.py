from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .config import ROOT, RuntimeCatalog, Settings
from .converter import STLJSONToStringConverter
from .knowledge import KnowledgeBase
from .services import StructuredLLM, TavilyService
from .validation import (
    atomic_write_json,
    enforce_semantic_completeness,
    json_text,
    normalize_global_semantics,
    rule_filter_candidates,
    validate_ast,
    validate_ast_against_semantics,
)


ProgressCallback = Callable[[str], None]


class GraphState(TypedDict, total=False):
    """LangGraph 在各节点之间传递的会话状态。"""

    session_id: str
    original_text: str
    started_at: float
    phase: str
    current_step: str
    signal_selection: dict[str, Any]
    signal_details: dict[str, Any]
    signal_context: str
    scene_signal_context: str
    global_semantics: dict[str, Any]
    semantic_history: list[dict[str, Any]]
    current_ambiguity: dict[str, Any]
    candidates: list[dict[str, Any]]
    search_results: list[dict[str, str]]
    user_update: str
    selected_candidate: dict[str, Any]
    proposed_revision: dict[str, Any]
    revision_feedback: str
    ast: dict[str, Any]
    stl: str
    stl_semantics: str
    validation_errors: list[str]
    ast_repairs: int
    result: dict[str, Any]
    status: str


def build_graph(
    settings: Settings | None = None,
    catalog: RuntimeCatalog | None = None,
    knowledge: KnowledgeBase | None = None,
    llm: StructuredLLM | None = None,
    tavily: TavilyService | None = None,
    progress: ProgressCallback | None = None,
):
    """构建以可修订全局语义为中心的 NL→STL 状态图。"""

    report = progress or (lambda _message: None)
    settings = settings or Settings.load()
    catalog = catalog or RuntimeCatalog()
    knowledge = knowledge or KnowledgeBase()
    llm = llm or StructuredLLM(settings, catalog, progress=report)
    tavily = tavily or TavilyService(settings, catalog, progress=report)

    def select_signals(state: GraphState) -> dict[str, Any]:
        """先用简短索引选择信号，再加载所选信号的详细定义。"""

        report("正在选择领域、场景与候选信号...")
        selection = knowledge.infer_selection(state["original_text"])
        errors: list[str] = []
        if selection is not None:
            report("已通过本地索引确定领域、场景与信号。")
        else:
            for _ in range(settings.max_llm_attempts):
                selection = llm.invoke(
                    "select_signals",
                    "signal_selection",
                    original_text=state["original_text"],
                    signals_index=knowledge.compact_index(),
                )
                errors = knowledge.validate_selection(selection)
                if not errors:
                    break
        if selection is None or errors:
            raise RuntimeError("信号选择无法通过知识库校验: " + "; ".join(errors))
        details = knowledge.signal_details(
            selection["domain"], selection["scenes"], selection["signals"]
        )
        scene_details = knowledge.signal_details(
            selection["domain"],
            selection["scenes"],
            sorted(knowledge.all_signal_names()),
        )
        return {
            "phase": "建立全局语义",
            "current_step": "信号选择完成",
            "signal_selection": selection,
            "signal_details": details,
            "signal_context": _signal_context(selection["domain"], details),
            "scene_signal_context": _signal_context(
                selection["domain"], scene_details
            ),
            "semantic_history": state.get("semantic_history", []),
            "ast_repairs": 0,
            "status": "running",
        }

    def initialize_semantics(state: GraphState) -> dict[str, Any]:
        """从原始 NL 初始化第一版统一全局语义。"""

        report("正在建立统一全局语义...")
        semantics = llm.invoke(
            "initialize_global_semantics",
            "global_semantics",
            original_text=state["original_text"],
            signal_details=state["signal_context"],
            operator_knowledge=knowledge.operators,
        )
        semantics["revision"] = 0
        normalize_global_semantics(semantics)
        enforce_semantic_completeness(semantics, state["original_text"], knowledge)
        _require_valid(catalog, "global_semantics", semantics, "初始全局语义")
        current = semantics["ambiguities"][0] if semantics["ambiguities"] else {}
        return {
            "global_semantics": semantics,
            "current_ambiguity": current,
            "phase": "需求澄清" if current else "生成 AST",
            "current_step": "全局语义已建立",
        }

    def route_after_initialization(state: GraphState) -> str:
        """初始语义已经过 Schema 约束，不再重复调用一次语义复核。"""

        return "prepare_candidates" if state.get("current_ambiguity") else "generate_ast"

    def review_semantics(state: GraphState) -> dict[str, Any]:
        """重新计算完整语义、映射和全部未解决问题。"""

        report("正在复核全局语义与全部模糊点...")
        current_revision = state["global_semantics"].get("revision", 0)
        reviewed = llm.invoke(
            "review_global_semantics",
            "global_semantics",
            original_text=state["original_text"],
            global_semantics=json_text(state["global_semantics"]),
            signal_details=state["signal_context"],
        )
        # 复核可以修改语义内容，但不能伪造一次新的用户修订版本。
        reviewed["revision"] = current_revision
        normalize_global_semantics(reviewed)
        enforce_semantic_completeness(reviewed, state["original_text"], knowledge)
        _require_valid(catalog, "global_semantics", reviewed, "复核后的全局语义")
        current = reviewed["ambiguities"][0] if reviewed["ambiguities"] else {}
        return {
            "global_semantics": reviewed,
            "current_ambiguity": current,
            "candidates": [],
            "search_results": [],
            "revision_feedback": "",
            "phase": "需求澄清" if current else "生成 AST",
            "current_step": "全局语义复核完成",
        }

    def route_after_review(state: GraphState) -> str:
        return "prepare_candidates" if state.get("current_ambiguity") else "generate_ast"

    def prepare_candidates(state: GraphState) -> dict[str, Any]:
        """按知识库、Tavily、LLM 推断的优先级准备简洁候选。"""

        ambiguity = state["current_ambiguity"]
        simple_candidates = _simple_reference_candidates(ambiguity)
        if simple_candidates:
            return {
                "phase": "需求澄清",
                "current_step": "参考值准备完成",
                "candidates": simple_candidates,
                "search_results": [],
            }

        valid_sources = _local_source_evidence(
            state["signal_selection"], state["signal_details"], knowledge.operators
        )
        required_signals = _ambiguity_signals(
            ambiguity, state["global_semantics"], knowledge.all_signal_names()
        )
        report("正在检索本地知识并生成候选...")
        local = llm.invoke(
            "generate_candidates_local",
            "candidate_set",
            original_text=state["original_text"],
            ambiguity=json_text(ambiguity),
            global_semantics=json_text(state["global_semantics"]),
            signal_details=state["scene_signal_context"],
            operator_knowledge=knowledge.operators,
        )
        allowed_signals = {
            name
            for signals in knowledge.signal_details(
                state["signal_selection"]["domain"],
                state["signal_selection"]["scenes"],
                sorted(knowledge.all_signal_names()),
            ).values()
            for name in signals
        }
        candidates, _ = rule_filter_candidates(
            local["candidates"],
            valid_sources,
            set(),
            allowed_signals,
            required_signals,
        )
        search_results: list[dict[str, str]] = []

        if len(candidates) < 2:
            report("本地知识不足，正在生成 Tavily 搜索词...")
            query = llm.invoke(
                "build_search_query",
                "search_query",
                original_text=state["original_text"],
                ambiguity=json_text(ambiguity),
                signal_details=state["scene_signal_context"],
            )["query"]
            report("正在使用 Tavily 搜索候选依据...")
            search_results = tavily.search(query)
            if search_results:
                report("正在根据搜索证据生成候选...")
                web = llm.invoke(
                    "generate_candidates_web",
                    "candidate_set",
                    original_text=state["original_text"],
                    ambiguity=json_text(ambiguity),
                    local_candidates=json_text(candidates),
                    search_results=json_text(search_results),
                    signal_details=state["scene_signal_context"],
                )
                candidates = _merge_candidates(candidates, web["candidates"])
                candidates, _ = rule_filter_candidates(
                    candidates,
                    valid_sources,
                    {item["url"]: item["content"] for item in search_results},
                    allowed_signals,
                    required_signals,
                )

        for _ in range(2):
            if len(candidates) >= 2:
                break
            report("正在补充明确标注的 LLM 工程候选...")
            inferred = llm.invoke(
                "generate_candidates_inference",
                "candidate_set",
                original_text=state["original_text"],
                ambiguity=json_text(ambiguity),
                existing_candidates=json_text(candidates),
                signal_details=state["scene_signal_context"],
            )
            candidates = _merge_candidates(candidates, inferred["candidates"])
            candidates, _ = rule_filter_candidates(
                candidates,
                valid_sources,
                {item["url"]: item["content"] for item in search_results},
                allowed_signals,
                required_signals,
            )

        if len(candidates) < 2:
            raise RuntimeError("未能生成至少 2 个通过规则校验的实质不同候选")
        return {
            "phase": "需求澄清",
            "current_step": "候选准备完成",
            "candidates": candidates[:3],
            "search_results": search_results,
        }

    def clarify(state: GraphState) -> dict[str, Any]:
        """暂停图；用户可以回答当前问题，也可以修订其它相关语义。"""

        report("")
        payload = {
            "phase": "需求澄清",
            "ambiguity": state["current_ambiguity"],
            "candidates": state["candidates"],
            "global_semantics": state["global_semantics"],
            "feedback": state.get("revision_feedback", ""),
        }
        answer = str(interrupt(payload)).strip()
        selected = _resolve_choice(answer, state["candidates"])
        return {
            "user_update": selected["value"] if selected else answer,
            "selected_candidate": selected or {},
            "revision_feedback": "",
            "current_step": "已接收用户输入",
        }

    def revise_semantics(state: GraphState) -> dict[str, Any]:
        """把本轮任意相关输入解释成一份完整的全局语义修订。"""

        report("正在理解输入并生成全局语义修订...")
        proposed = llm.invoke(
            "revise_global_semantics",
            "semantic_revision",
            original_text=state["original_text"],
            current_ambiguity=json_text(state.get("current_ambiguity", {})),
            global_semantics=json_text(state["global_semantics"]),
            user_input=state["user_update"],
            selected_candidate=json_text(state.get("selected_candidate", {})),
            signal_details=state["scene_signal_context"],
        )
        if proposed.get("applicable"):
            # 是否还存在问题由 revised_semantics.ambiguities 和确定性完整性检查决定，
            # 不接受模型同时给出 applicable=true/needs_follow_up=true 的矛盾控制信号。
            proposed["needs_follow_up"] = False
            proposed["follow_up_question"] = None
            revised = proposed["revised_semantics"]
            revised["revision"] = state["global_semantics"].get("revision", 0) + 1
            normalize_global_semantics(revised)
            enforce_semantic_completeness(revised, state["original_text"], knowledge)
            errors = catalog.validate("global_semantics", revised)
            if errors:
                proposed["applicable"] = False
                proposed["needs_follow_up"] = True
                proposed["reason"] = "修订后的全局语义格式无效：" + "; ".join(errors)
                proposed["follow_up_question"] = "请换一种方式说明本次修改。"
        return {"proposed_revision": proposed, "current_step": "语义修订已生成"}

    def validate_revision(state: GraphState) -> dict[str, Any]:
        """应用已通过结构与完整性检查的用户修订。"""

        proposed = state["proposed_revision"]
        if not proposed.get("applicable") or proposed.get("needs_follow_up"):
            feedback = proposed.get("reason", "输入不足以更新全局语义")
            if proposed.get("follow_up_question"):
                feedback += "；" + proposed["follow_up_question"]
            return {"revision_feedback": feedback, "current_step": "语义修订需要补充"}

        history = list(state.get("semantic_history", []))
        history.append(
            {
                "revision": state["global_semantics"].get("revision", 0),
                "semantics": state["global_semantics"],
                "user_update": state["user_update"],
                "change_summary": proposed["change_summary"],
            }
        )
        revised = proposed["revised_semantics"]
        current = revised.get("ambiguities", [{}])[0] if revised.get("ambiguities") else {}
        return {
            "global_semantics": revised,
            "semantic_history": history,
            "proposed_revision": {},
            "revision_feedback": "",
            "current_ambiguity": current,
            "candidates": [],
            "phase": "需求澄清" if current else "生成 AST",
            "current_step": "全局语义已更新",
        }

    def route_after_revision(state: GraphState) -> str:
        if state.get("revision_feedback"):
            return "clarify"
        if state.get("current_ambiguity"):
            return "prepare_candidates"
        return "generate_ast"

    def generate_ast(state: GraphState) -> dict[str, Any]:
        """只根据当前全局语义生成 AST。"""

        report("正在根据当前全局语义生成 AST...")
        ast = llm.invoke(
            "generate_ast",
            output_schema=knowledge.ast_schema,
            original_text=state["original_text"],
            global_semantics=json_text(state["global_semantics"]),
            signal_details=state["scene_signal_context"],
        )
        return {
            "phase": "验证 AST",
            "current_step": "AST 已生成",
            "ast": ast,
            "validation_errors": [],
        }

    def validate_generated_ast(state: GraphState) -> dict[str, Any]:
        """验证 AST 结构，并禁止加入当前全局语义中不存在的信号。"""

        report("正在验证 AST Schema、信号与时间区间...")
        errors = validate_ast(state["ast"], knowledge)
        errors.extend(
            validate_ast_against_semantics(
                state["ast"], state["global_semantics"], knowledge
            )
        )
        if errors:
            return {"validation_errors": list(dict.fromkeys(errors))}
        try:
            stl = STLJSONToStringConverter().convert(state["ast"])
        except Exception as exc:
            return {"validation_errors": [f"AST 转 STL 失败: {exc}"]}
        return {"stl": stl, "validation_errors": [], "current_step": "AST 验证通过"}

    def route_after_ast_validation(state: GraphState) -> str:
        if not state.get("validation_errors"):
            return "finalize"
        if state.get("ast_repairs", 0) >= settings.max_ast_repairs:
            return "fail"
        return "repair_ast"

    def repair_ast(state: GraphState) -> dict[str, Any]:
        """在当前全局语义边界内修复 AST。"""

        attempt = state.get("ast_repairs", 0) + 1
        report(f"正在修复 AST（{attempt}/{settings.max_ast_repairs}）...")
        ast = llm.invoke(
            "repair_ast",
            output_schema=knowledge.ast_schema,
            original_text=state["original_text"],
            global_semantics=json_text(state["global_semantics"]),
            ast=json_text(state["ast"]),
            validation_errors=json_text(state["validation_errors"]),
            signal_details=state["scene_signal_context"],
        )
        return {
            "ast": ast,
            "ast_repairs": attempt,
            "validation_errors": [],
            "phase": "修复并重新验证 AST",
            "current_step": f"AST 第 {attempt} 次修复完成",
        }

    def finalize(state: GraphState) -> dict[str, Any]:
        """落盘 AST，并最终执行用户提供的验证和转换脚本。"""

        session_dir = ROOT / "tmp" / state["session_id"]
        ast_path = session_dir / "ast.json"
        atomic_write_json(ast_path, state["ast"])
        report("正在执行 validate_ast.py...")
        validation = _run_script(ROOT / "src" / "validate_ast.py", ast_path)
        report("正在执行 ast2stl.py 并精简无意义括号...")
        conversion = _run_script(ROOT / "src" / "ast2stl.py", ast_path)
        if validation["returncode"] != 0 or conversion["returncode"] != 0:
            return {
                "status": "error",
                "phase": "验证失败",
                "result": {
                    "errors": [validation["output"], conversion["output"]],
                    "ast_path": str(ast_path),
                },
            }
        result = {
            "original_text": state["original_text"],
            "global_semantics": state["global_semantics"],
            "mappings": state["global_semantics"].get("mappings", []),
            "ast": state["ast"],
            "ast_path": str(ast_path),
            "stl": conversion["output"].strip(),
            "stl_semantics": _stl_semantics(state),
            "schema_validation": validation["output"].strip(),
            "elapsed_seconds": round(max(0.0, time.monotonic() - state["started_at"]), 3),
        }
        result_errors = catalog.validate("final_result", result)
        if result_errors:
            return {
                "status": "error",
                "phase": "验证失败",
                "result": {"errors": result_errors, "ast_path": str(ast_path)},
            }
        report("")
        return {
            "status": "complete",
            "phase": "完成",
            "current_step": "完成",
            "result": result,
        }

    def fail(state: GraphState) -> dict[str, Any]:
        report("")
        return {
            "status": "error",
            "phase": "验证失败",
            "result": {"errors": state.get("validation_errors", [])},
        }

    builder = StateGraph(GraphState)
    builder.add_node("select_signals", select_signals)
    builder.add_node("initialize_semantics", initialize_semantics)
    builder.add_node("review_semantics", review_semantics)
    builder.add_node("prepare_candidates", prepare_candidates)
    builder.add_node("clarify", clarify)
    builder.add_node("revise_semantics", revise_semantics)
    builder.add_node("validate_revision", validate_revision)
    builder.add_node("generate_ast", generate_ast)
    builder.add_node("validate_ast", validate_generated_ast)
    builder.add_node("repair_ast", repair_ast)
    builder.add_node("finalize", finalize)
    builder.add_node("fail", fail)
    builder.add_edge(START, "select_signals")
    builder.add_edge("select_signals", "initialize_semantics")
    builder.add_conditional_edges("initialize_semantics", route_after_initialization)
    builder.add_conditional_edges("review_semantics", route_after_review)
    builder.add_edge("prepare_candidates", "clarify")
    builder.add_edge("clarify", "revise_semantics")
    builder.add_edge("revise_semantics", "validate_revision")
    builder.add_conditional_edges("validate_revision", route_after_revision)
    builder.add_edge("generate_ast", "validate_ast")
    builder.add_conditional_edges("validate_ast", route_after_ast_validation)
    builder.add_edge("repair_ast", "validate_ast")
    builder.add_edge("finalize", END)
    builder.add_edge("fail", END)
    return builder.compile(checkpointer=InMemorySaver())


def initial_state(text: str, session_id: str | None = None) -> GraphState:
    """创建一个相互隔离的新翻译会话。"""

    return {
        "session_id": session_id or uuid.uuid4().hex[:12],
        "original_text": text,
        "started_at": time.monotonic(),
        "phase": "选择信号",
        "current_step": "准备开始",
        "semantic_history": [],
        "ast_repairs": 0,
        "status": "running",
    }


def _signal_context(domain: str, details: dict[str, Any]) -> str:
    """将精确检索的信号定义整理成带来源标识的模型上下文。"""

    lines = [f"领域: {domain}"]
    for scene, signals in details.items():
        lines.append(f"场景: {scene}")
        for name, description in signals.items():
            lines.append(
                f"- {name}: {description} [来源: signals_explain.txt#{domain}/{scene}/{name}]"
            )
    return "\n".join(lines)


def _local_source_evidence(
    selection: dict[str, Any], details: dict[str, Any], operators: str
) -> dict[str, str]:
    """建立来源 ID 到原始证据文本的映射，供候选真实性检查。"""

    domain = selection["domain"]
    sources = {"stl_operators.md": operators}
    for scene, signals in details.items():
        for name, description in signals.items():
            sources[f"signals_explain.txt#{domain}/{scene}/{name}"] = description
    return sources


def _merge_candidates(
    first: list[dict[str, Any]], second: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [dict(item) for item in first + second]


def _simple_reference_candidates(ambiguity: dict[str, Any]) -> list[dict[str, Any]]:
    """对纯数值槽位给本地参考值，避免搜索结果答非所问。"""

    text = " ".join(
        str(ambiguity.get(key, ""))
        for key in ("nl_fragment", "description", "question", "category")
    ).lower()
    if "few seconds" in text or "几秒" in text or (
        ambiguity.get("category") == "time" and ("second" in text or "秒" in text)
    ):
        values = [
            ("2 s", "短时间窗口常用参考值"),
            ("3 s", "few seconds 的常用解释"),
            ("5 s", "较宽松的短时间窗口"),
        ]
    elif "meter" in text or "meters" in text or "米" in text:
        values = [("5 m", "较小距离阈值参考"), ("10 m", "常用整数距离阈值参考")]
    else:
        return []
    return [
        {
            "id": f"ref_{index}",
            "value": value,
            "explanation": explanation,
            "source_type": "llm_generated",
            "source_reference": "本地参考值，需用户确认",
            "canonical": value.lower().replace(" ", ""),
        }
        for index, (value, explanation) in enumerate(values, start=1)
    ]


def _ambiguity_signals(
    ambiguity: dict[str, Any], semantics: dict[str, Any], known: set[str]
) -> set[str]:
    """提取当前模糊谓词已有的信号，候选必须直接围绕这些信号。"""

    ambiguity_id = str(ambiguity.get("id", ""))
    parameter = ambiguity_id.removeprefix("unbound_parameter_")
    nl_fragment = str(ambiguity.get("nl_fragment", ""))
    signals: set[str] = set()
    for item in semantics.get("items", []):
        if not isinstance(item, dict):
            continue
        fragment = str(item.get("stl_fragment", ""))
        if (parameter and parameter in fragment) or (
            nl_fragment and item.get("nl_fragment") == nl_fragment
        ):
            signals.update(_known_formula_signals(fragment, known))
    return signals


def _known_formula_signals(text: str, known: set[str]) -> set[str]:
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))
    return identifiers & known


def _resolve_choice(
    answer: str, candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """兼容字母、数字、候选 ID 和完整候选文本四种选择方式。"""

    normalized = answer.strip().upper()
    labels = {chr(ord("A") + index): item for index, item in enumerate(candidates)}
    if normalized in labels:
        return labels[normalized]
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(candidates):
            return candidates[index]
    return next(
        (item for item in candidates if answer.strip() in {item["id"], item["value"]}),
        None,
    )


def _run_script(script: Path, ast_path: Path) -> dict[str, Any]:
    """隔离执行既有脚本，并保留退出码和标准输出用于最终判定。"""

    completed = subprocess.run(
        [sys.executable, str(script), str(ast_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip()
    return {"returncode": completed.returncode, "output": output}


def _stl_semantics(state: GraphState) -> str:
    original = str(state.get("original_text", ""))
    chinese = _is_chinese(original)
    clear_text = _clarified_original_text(original, state)
    if clear_text and not _contains_unresolved_terms(clear_text):
        return clear_text
    prefix = "清晰化需求：" if chinese else "Clarified requirement: "
    punctuation = "。" if chinese else "."
    return (
        f"{prefix}"
        f"{_describe_formula(state['ast'], state.get('global_semantics', {}), chinese)}"
        f"{punctuation}"
    )


def _clarified_original_text(original: str, state: GraphState) -> str:
    if not original:
        return ""
    text = original.strip()
    ast = state.get("ast", {})
    semantics = state.get("global_semantics", {})
    replacements = _clarification_replacements(ast, semantics, _is_chinese(text), text)
    for old, new in replacements:
        text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
    text = _clean_clarified_text(text)
    if text == original.strip():
        return ""
    return text


def _clarification_replacements(
    ast: dict[str, Any], semantics: dict[str, Any], chinese: bool, original: str
) -> list[tuple[str, str]]:
    replacements: list[tuple[str, str]] = []
    interval = _top_level_interval(ast)
    if interval:
        if chinese:
            replacements.extend([
                ("未来几秒", f"未来 {interval} 秒"),
                ("接下来几秒", f"接下来 {interval} 秒"),
                ("几秒", f"{interval} 秒"),
            ])
        else:
            replacements.extend([
                ("the next few seconds", f"the next {interval} seconds"),
                ("next few seconds", f"next {interval} seconds"),
                ("a few seconds", f"{interval} seconds"),
                ("few seconds", f"{interval} seconds"),
            ])
    threshold = _main_numeric_threshold(ast)
    if threshold is not None:
        unit = _threshold_unit(semantics, chinese, original)
        if chinese:
            replacements.extend([
                ("一些米", f"{threshold}{unit}"),
                ("若干米", f"{threshold}{unit}"),
                ("某个米数", f"{threshold}{unit}"),
            ])
        else:
            replacements.extend([
                ("some meters", f"{threshold} {unit}"),
                ("some metres", f"{threshold} {unit}"),
                ("some meter", f"{threshold} {unit}"),
                ("some metre", f"{threshold} {unit}"),
            ])
    predicate = _main_predicate_constant(ast)
    if predicate is not None:
        value = _format_value_with_unit(
            predicate["value"],
            _unit_for_predicate_info(predicate, semantics, chinese, original),
            chinese,
        )
        if chinese:
            relation = _relation_text(str(predicate["relation"]), chinese=True)
            replacements.extend([
                ("保持低速", f"保持{relation}{value}"),
                ("低速", f"{relation}{value}"),
            ])
        else:
            relation = _low_speed_relation_text(str(predicate["relation"]))
            replacements.extend([
                ("shall remain low speed", f"shall remain {relation} {value}"),
                ("remain low speed", f"remain {relation} {value}"),
                ("low speed", f"{relation} {value}"),
            ])
    return replacements


def _top_level_interval(ast: dict[str, Any]) -> str:
    if ast.get("nodeType") != "temporal":
        return ""
    interval = ast.get("interval")
    if not isinstance(interval, dict):
        return ""
    lower = interval.get("lower", 0)
    upper = interval.get("upper", "inf")
    if lower == 0 and upper != "inf":
        return _format_number(upper)
    return ""


def _main_numeric_threshold(ast: dict[str, Any]) -> str | None:
    predicate = _main_predicate_constant(ast)
    return _format_number(predicate["value"]) if predicate is not None else None


def _main_predicate_constant(ast: dict[str, Any]) -> dict[str, Any] | None:
    values: list[Any] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("nodeType") == "predicate":
                right = value.get("right", {})
                if isinstance(right, dict) and right.get("exprType") == "constant":
                    values.append(
                        {
                            "relation": value.get("relation"),
                            "value": right.get("value"),
                            "signal": _predicate_signal_name(value),
                        }
                    )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(ast)
    numeric = [
        value for value in values if isinstance(value.get("value"), (int, float))
    ]
    return numeric[-1] if numeric else None


def _threshold_unit(semantics: dict[str, Any], chinese: bool, original: str = "") -> str:
    text = (json.dumps(semantics, ensure_ascii=False) + " " + original).lower()
    if "km/h" in text or "km / h" in text or "千米每小时" in text or "公里每小时" in text:
        return "km/h"
    if "meter" in text or "metre" in text or "单位 m" in text or "→ m" in text:
        return "米" if chinese else "meters"
    if "second" in text or "单位 s" in text or "→ s" in text:
        return "秒" if chinese else "seconds"
    return ""


def _unit_for_predicate_info(
    predicate: dict[str, Any],
    semantics: dict[str, Any],
    chinese: bool,
    original: str = "",
) -> str:
    signal = str(predicate.get("signal", "")).lower()
    if signal and ("speed" in signal or signal in {"ego_speed"}):
        return "km/h"
    if signal and "distance" in signal:
        return "米" if chinese else "meters"
    if signal and ("time" in signal or signal.endswith("_ttc") or signal == "ttc"):
        return "秒" if chinese else "seconds"
    return _threshold_unit(semantics, chinese, original)


def _format_value_with_unit(value: Any, unit: str, chinese: bool) -> str:
    number = _format_number(value)
    if not unit:
        return number
    if unit == "km/h":
        return f"{number} {unit}"
    return f"{number}{unit}" if chinese else f"{number} {unit}"


def _format_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _is_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _clean_clarified_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _contains_unresolved_terms(text: str) -> bool:
    normalized = text.lower()
    terms = (
        "low speed",
        "safe distance",
        "few seconds",
        "some meters",
        "some metres",
        "threshold",
        "pending",
        "低速",
        "安全距离",
        "几秒",
        "若干",
        "一些",
        "待确认",
        "待澄清",
    )
    return any(term in normalized for term in terms)


def _describe_formula(
    node: dict[str, Any], semantics: dict[str, Any] | None = None, chinese: bool = True
) -> str:
    semantics = semantics or {}
    node_type = node.get("nodeType")
    if node_type == "predicate":
        return _describe_predicate(node, semantics, chinese)
    if node_type == "boolean":
        return _describe_boolean(node, semantics, chinese)
    if node_type == "temporal":
        return _describe_temporal(node, semantics, chinese)
    if node_type == "pastTemporal":
        operator = node.get("operator")
        operand = _describe_formula(node.get("operands", [{}])[0], semantics, chinese)
        interval = _describe_interval(node.get("interval"), chinese)
        if not chinese:
            if operator == "historically":
                return f"throughout {interval}, {operand} held"
            if operator == "once":
                return f"at some time in {interval}, {operand} held"
            if operator == "since":
                operands = node.get("operands", [{}, {}])
                return (
                    f"{_describe_formula(operands[0], semantics, chinese)} has held "
                    f"since {_describe_formula(operands[1], semantics, chinese)}"
                )
        if operator == "historically":
            return f"在过去{interval}内，{operand}始终成立"
        if operator == "once":
            return f"在过去{interval}内，存在某个时刻满足：{operand}"
        if operator == "since":
            operands = node.get("operands", [{}, {}])
            return (
                f"{_describe_formula(operands[0], semantics, chinese)} 自 "
                f"{_describe_formula(operands[1], semantics, chinese)} 后成立"
            )
    if node_type == "edge":
        operand = _describe_formula(node.get("operand", {}), semantics, chinese)
        return (
            f"{node.get('operator')}({operand}) 发生"
            if chinese
            else f"{node.get('operator')}({operand}) occurs"
        )
    return "最终公式成立"


def _describe_temporal(
    node: dict[str, Any], semantics: dict[str, Any], chinese: bool
) -> str:
    operator = node.get("operator")
    operands = node.get("operands", [])
    interval = _describe_interval(node.get("interval"), chinese)
    if operator == "always" and operands:
        if not chinese:
            if operands[0].get("nodeType") == "predicate":
                return f"For {interval}, {_describe_persistent_predicate(operands[0], semantics, chinese)}"
            return (
                f"For {interval}, "
                f"{_describe_formula(operands[0], semantics, chinese)} shall always hold"
            )
        if operands[0].get("nodeType") == "predicate":
            return f"在{interval}内，{_describe_persistent_predicate(operands[0], semantics, chinese)}"
        return f"在{interval}内，{_describe_formula(operands[0], semantics, chinese)}始终成立"
    if operator == "eventually" and operands:
        if not chinese:
            return (
                f"At some time within {interval}, "
                f"{_describe_formula(operands[0], semantics, chinese)}"
            )
        return f"在{interval}内，存在某个时刻满足：{_describe_formula(operands[0], semantics, chinese)}"
    if operator in {"until", "weak_until", "release"} and len(operands) >= 2:
        left = _describe_formula(operands[0], semantics, chinese)
        right = _describe_formula(operands[1], semantics, chinese)
        return f"在{interval}内，{left} {operator} {right}"
    return "时序条件成立"


def _describe_boolean(
    node: dict[str, Any], semantics: dict[str, Any], chinese: bool
) -> str:
    operator = node.get("operator")
    operands = [
        _describe_formula(item, semantics, chinese) for item in node.get("operands", [])
    ]
    if not chinese:
        if operator == "not" and operands:
            return f"not ({operands[0]})"
        if operator == "and":
            return " and ".join(operands)
        if operator == "or":
            return " or ".join(operands)
        if operator == "implies" and len(operands) >= 2:
            return f"if {operands[0]}, then {operands[1]}"
        if operator == "iff" and len(operands) >= 2:
            return f"{operands[0]} if and only if {operands[1]}"
    if operator == "not" and operands:
        return f"不满足：{operands[0]}"
    if operator == "and":
        return "且".join(operands)
    if operator == "or":
        return "或".join(operands)
    if operator == "implies" and len(operands) >= 2:
        return f"如果{operands[0]}，则{operands[1]}"
    if operator == "iff" and len(operands) >= 2:
        return f"{operands[0]} 当且仅当 {operands[1]}"
    return "逻辑条件成立"


def _describe_predicate(
    node: dict[str, Any], semantics: dict[str, Any], chinese: bool
) -> str:
    left = _describe_expression(node.get("left", {}))
    right = _describe_right_expression(node, semantics, chinese)
    relation = _relation_text(str(node.get("relation")), chinese)
    if not chinese:
        return f"{left} is {relation} {right}"
    return f"{left} {relation} {right}"


def _describe_persistent_predicate(
    node: dict[str, Any], semantics: dict[str, Any], chinese: bool
) -> str:
    left = _describe_expression(node.get("left", {}))
    right = _describe_right_expression(node, semantics, chinese)
    relation = _relation_text(str(node.get("relation")), chinese)
    if not chinese:
        return f"{left} shall always be {relation} {right}"
    return f"{left} 始终{relation} {right}"


def _relation_text(relation: str, chinese: bool = True) -> str:
    if not chinese:
        return {
            ">": "greater than",
            ">=": "greater than or equal to",
            "<": "less than",
            "<=": "less than or equal to",
            "==": "equal to",
            "!=": "not equal to",
        }.get(relation, relation)
    return {
        ">": "大于",
        ">=": "大于等于",
        "<": "小于",
        "<=": "小于等于",
        "==": "等于",
        "!=": "不等于",
    }.get(relation, relation)


def _low_speed_relation_text(relation: str) -> str:
    return {
        "<": "below",
        "<=": "at or below",
        ">": "above",
        ">=": "at or above",
        "==": "equal to",
        "!=": "not equal to",
    }.get(relation, _relation_text(relation, chinese=False))


def _describe_right_expression(
    node: dict[str, Any], semantics: dict[str, Any], chinese: bool
) -> str:
    right = node.get("right", {})
    if isinstance(right, dict) and right.get("exprType") == "constant":
        return _format_value_with_unit(
            right.get("value"),
            _unit_for_predicate_info(
                {
                    "signal": _predicate_signal_name(node),
                    "value": right.get("value"),
                    "relation": node.get("relation"),
                },
                semantics,
                chinese,
            ),
            chinese,
        )
    return _describe_expression(right)


def _predicate_signal_name(node: dict[str, Any]) -> str:
    left = node.get("left", {})
    if isinstance(left, dict) and left.get("exprType") == "signal":
        return str(left.get("name", ""))
    return ""


def _describe_expression(expr: dict[str, Any]) -> str:
    expr_type = expr.get("exprType")
    if expr_type == "signal":
        return str(expr.get("name", ""))
    if expr_type == "constant":
        return str(expr.get("value", ""))
    if expr_type == "parameter":
        return str(expr.get("name", ""))
    if expr_type == "binary":
        left = _describe_expression(expr.get("left", {}))
        right = _describe_expression(expr.get("right", {}))
        op = {
            "add": " + ",
            "subtract": " - ",
            "multiply": " * ",
            "divide": " / ",
        }.get(str(expr.get("operator")), f" {expr.get('operator')} ")
        return f"{left}{op}{right}"
    return ""


def _describe_interval(interval: dict[str, Any] | None, chinese: bool = True) -> str:
    if not interval:
        return "整个监控区间" if chinese else "the entire monitoring interval"
    lower = interval.get("lower", 0)
    upper = interval.get("upper", "inf")
    if lower == 0 and upper == "inf":
        return "整个监控区间" if chinese else "the entire monitoring interval"
    if lower == 0:
        return f"未来 {upper} 秒" if chinese else f"the next {upper} seconds"
    return f"{lower} 到 {upper} 秒" if chinese else f"{lower} to {upper} seconds"


def _require_valid(
    catalog: RuntimeCatalog, format_id: str, value: Any, label: str
) -> None:
    errors = catalog.validate(format_id, value)
    if errors:
        raise RuntimeError(f"{label}未通过格式校验: {'; '.join(errors)}")
