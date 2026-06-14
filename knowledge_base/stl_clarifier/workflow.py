from __future__ import annotations

import json
import re
import time
from collections.abc import Callable

from .graph import (
    advance_state,
    executable_candidates,
    ensure_required_ambiguities,
    generate_local_candidates,
    local_evidence_problem,
    remove_current_ambiguity,
    resolve_answer,
    sanitize_candidates,
    validate_formula,
)
from .knowledge import KnowledgeBase
from .prompts import (
    ANALYZE_SYSTEM,
    ASSESS_SYSTEM,
    ASSESS_SEARCH_RELEVANCE_SYSTEM,
    CANDIDATE_REVIEW_SYSTEM,
    GENERATE_SEMANTIC_PLAN_SYSTEM,
    LLM_INFERENCE_CANDIDATES_SYSTEM,
    LOCAL_KNOWLEDGE_CANDIDATES_SYSTEM,
    VALIDATE_CUSTOM_ANSWER_SYSTEM,
    WEB_CANDIDATES_SYSTEM,
)
from .schemas import (
    Ambiguity,
    AmbiguityAnalysis,
    AnswerAssessment,
    Candidate,
    CandidateAssessment,
    CandidateReviewSet,
    CandidateSet,
    Clarification,
    DomainContext,
    GraphState,
    SearchResult,
    SearchRelevanceAssessment,
    SemanticPlan,
    SourceType,
    STLResult,
)
from .services import ChatAnywhereService, TavilyService
from .semantics import (
    SemanticCompiler,
    SemanticValidationError,
    normalize_standard_conversions,
    validate_plan_provenance,
)


Progress = Callable[[str], None]
AskUser = Callable[[Ambiguity, list[Candidate]], str]
InteractionUpdate = Callable[[list[Ambiguity], list[Clarification]], None]
MAX_SEMANTIC_PLAN_ATTEMPTS = 3


class ClarificationWorkflow:
    def __init__(
        self,
        chat: ChatAnywhereService,
        tavily: TavilyService,
        knowledge: KnowledgeBase,
        progress: Progress,
        interaction_update: InteractionUpdate | None = None,
    ) -> None:
        self.chat = chat
        self.tavily = tavily
        self.knowledge = knowledge
        self.progress = progress
        self.interaction_update = interaction_update or (lambda _pending, _resolved: None)

    def close(self) -> None:
        self.chat.close()
        self.tavily.close()

    def run(self, description: str, ask_user: AskUser) -> tuple[STLResult, list[str]]:
        analysis_evidence = self.knowledge.retrieve(description, description, limit=16)
        analysis = self._step(
            "1/4 正在调用 ChatAnywhere 分析领域、场景和歧义",
            lambda: self.chat.generate(
                AmbiguityAnalysis,
                ANALYZE_SYSTEM,
                f"原始需求：{description}\n\n已有澄清：[]\n\n"
                f"相关本地信号与算子知识：\n{analysis_evidence.context}",
            ),
        )
        context = analysis.context
        context = context.model_copy(
            update={"knowledge_scenes": self._resolve_knowledge_scenes(context)}
        )
        self.progress(
            f"识别结果：领域={context.domain}；场景={context.scene}；主体={context.subject}"
        )
        analyzed_ambiguities = analysis.ambiguities
        if len(context.knowledge_scenes) == 1:
            analyzed_ambiguities = [
                item for item in analyzed_ambiguities if item.category != "signal"
            ]
            self.progress(
                f"已自动绑定知识库场景：{context.knowledge_scenes[0]}；不再询问底层信号名"
            )
        ambiguities = ensure_required_ambiguities(description, analyzed_ambiguities, [])
        state: GraphState = advance_state(
            {
                "original_text": description,
                "ambiguities": [item.model_dump(mode="json") for item in ambiguities],
                "clarifications": [],
            }
        )

        while state.get("current_ambiguity"):
            ambiguity = Ambiguity.model_validate(state["current_ambiguity"])
            contextual_query = " ".join(
                [
                    ambiguity.knowledge_query,
                    context.domain,
                    context.scene,
                    context.subject,
                    *context.quantities,
                    *context.search_keywords,
                ]
            )
            evidence = self.knowledge.retrieve_for_scenes(
                description,
                contextual_query,
                context.knowledge_scenes,
            )
            state["local_context"] = evidence.context
            state["local_source_ids"] = evidence.source_ids
            candidates = generate_local_candidates(state)
            candidates, _ = executable_candidates(
                ambiguity, candidates, self.knowledge.signal_names()
            )
            if not candidates:
                candidates = self._local_knowledge_candidates(
                    context, ambiguity, evidence.context, evidence.source_ids
                )
            if len(candidates) < 2:
                candidates = self._external_candidates(
                    description,
                    context,
                    ambiguity,
                    evidence.context,
                    evidence.source_ids,
                )
            candidates = self._review_and_regenerate_candidates(
                description,
                context,
                ambiguity,
                candidates,
                evidence.context,
                evidence.source_ids,
            )
            self.interaction_update(
                [Ambiguity.model_validate(item) for item in state.get("ambiguities", [])],
                [Clarification.model_validate(item) for item in state.get("clarifications", [])],
            )
            value, selected = self._obtain_valid_answer(
                description,
                context,
                ambiguity,
                candidates,
                evidence.context,
                ask_user,
            )
            clarification = Clarification(
                ambiguity_id=ambiguity.id,
                ambiguity_description=ambiguity.description,
                issue_type=ambiguity.issue_type,
                category=ambiguity.category,
                question=ambiguity.question,
                answer=value,
                supporting_text=selected.explanation if selected else "",
                semantic_role=self._semantic_role(ambiguity),
                selected_candidate_id=selected.id if selected else None,
                source_type=selected.source_type if selected else SourceType.USER_INPUT,
                source_reference=(
                    selected.source_reference
                    if selected
                    else "用户输入（经 LLM 有效性校验与规范化）"
                ),
            )
            state["clarifications"] = [
                *state.get("clarifications", []),
                clarification.model_dump(mode="json"),
            ]
            state = remove_current_ambiguity(state)

        result = self._generate_compiled_result(
            description,
            context,
            [Clarification.model_validate(item) for item in state.get("clarifications", [])],
        )
        errors = validate_formula(result.formula, result.signals_used, self.knowledge.signal_names())
        return result, errors

    @staticmethod
    def _semantic_role(ambiguity: Ambiguity) -> str:
        text = f"{ambiguity.id} {ambiguity.description} {ambiguity.question}"
        if ambiguity.category == "scope":
            return "scope"
        if ambiguity.id == "define_braking_response_deadline" or any(
            token in text for token in ("响应时限", "及时刹车", "多长时间内")
        ):
            return "response_deadline"
        if ambiguity.id == "define_braking_trigger" or any(
            token in text for token in ("触发条件", "必要的时候", "刹车时机")
        ):
            return "response_trigger"
        if ambiguity.category == "time":
            return "temporal_scope"
        return "predicate"

    def _generate_compiled_result(
        self,
        description: str,
        context: DomainContext,
        clarifications: list[Clarification],
    ) -> STLResult:
        evidence = self.knowledge.retrieve_for_scenes(
            description,
            "STL formula signals operators units",
            context.knowledge_scenes,
            limit=20,
        )
        feedback = ""
        last_error: SemanticValidationError | None = None
        for attempt in range(1, MAX_SEMANTIC_PLAN_ATTEMPTS + 1):
            plan = self._step(
                "4/4 正在调用 ChatAnywhere 构建类型化 STL 语义",
                lambda: self.chat.generate(
                    SemanticPlan,
                    GENERATE_SEMANTIC_PLAN_SYSTEM,
                    f"原始需求：{description}\n\n"
                    f"领域与场景：\n{context.model_dump_json(indent=2)}\n\n"
                    f"已确认澄清：\n{_json([item.model_dump(mode='json') for item in clarifications])}\n\n"
                    f"信号和单位知识：\n{evidence.context}\n\n"
                    f"上一轮本地类型检查反馈：\n{feedback or '无'}",
                ),
            )
            try:
                signal_units = self.knowledge.signal_units(context.knowledge_scenes)
                plan = normalize_standard_conversions(plan, signal_units)
                validate_plan_provenance(plan, clarifications, description)
                compiler = SemanticCompiler(signal_units)
                return compiler.compile(plan)
            except SemanticValidationError as exc:
                last_error = exc
                feedback = (
                    f"第 {attempt} 轮 SemanticPlan 未通过本地类型/量纲检查：{exc}。"
                    "请保持用户已确认语义不变，只修正结构、单位或需求类型；"
                    "不得自行补充用户未确认的信息。"
                )
                self.progress(feedback)
        raise RuntimeError(
            f"类型化语义连续 {MAX_SEMANTIC_PLAN_ATTEMPTS} 次未通过本地校验：{last_error}"
        )

    @staticmethod
    def _resolve_knowledge_scenes(context: DomainContext) -> list[str]:
        text = f"{context.domain} {context.scene} {' '.join(context.search_keywords)}".lower()
        provided = list(dict.fromkeys(context.knowledge_scenes))
        if provided:
            if "AEB" in provided and any(word in text for word in ("紧急制动", "制动控制", "及时刹车")):
                return ["AEB"]
            return provided
        aliases = [
            (("紧急制动", "aeb"), "AEB"),
            (("跟车", "车距保持", "acc"), "ACC"),
            (("泊车", "停车", "parking"), "Parking"),
            (("限速", "speed limit"), "Speed_Limit"),
            (("牵引力", "traction"), "Traction_Control"),
            (("车道保持", "lane keeping"), "Lane_Keeping"),
            (("变道", "lane change"), "Lane_Change"),
        ]
        matches = [scene for keywords, scene in aliases if any(keyword in text for keyword in keywords)]
        if "制动" in text and "AEB" not in matches:
            matches.insert(0, "AEB")
        return list(dict.fromkeys(matches))

    def _local_knowledge_candidates(
        self,
        context: DomainContext,
        ambiguity: Ambiguity,
        local_context: str,
        local_source_ids: list[str],
    ) -> list[Candidate]:
        if not local_context.strip():
            return []
        system_prompt = (
            LOCAL_KNOWLEDGE_CANDIDATES_SYSTEM
            if ambiguity.category == "signal"
            else ASSESS_SYSTEM
        )
        assessment = self._step(
            "正在调用 ChatAnywhere 生成本地知识候选项",
            lambda: self.chat.generate(
                CandidateAssessment,
                system_prompt,
                f"领域与场景：\n{context.model_dump_json(indent=2)}\n\n"
                f"当前歧义：\n{ambiguity.model_dump_json(indent=2)}\n\n"
                f"本地知识：\n{local_context}",
            ),
        )
        candidates = sanitize_candidates(
            assessment.candidates,
            set(local_source_ids),
            set(),
        )
        candidates, rejected = executable_candidates(
            ambiguity, candidates, self.knowledge.signal_names()
        )
        evidence_rejected: list[str] = []
        evidence_valid: list[Candidate] = []
        for candidate in candidates:
            problem = local_evidence_problem(candidate, local_context)
            if problem:
                evidence_rejected.append(f"{candidate.id}: {problem}")
            else:
                evidence_valid.append(candidate)
        candidates = evidence_valid
        rejected.extend(evidence_rejected)
        if rejected:
            self.progress(f"已拒绝不可执行的本地候选：{'；'.join(rejected)}")
        if assessment.local_knowledge_sufficient and len(candidates) >= 2:
            self.progress("候选项来源：本地知识库（无需外部搜索）")
            return candidates
        self.progress("本地知识不足以形成至少 2 个有效候选，进入 Tavily 搜索")
        return []

    def _obtain_valid_answer(
        self,
        description: str,
        context: DomainContext,
        ambiguity: Ambiguity,
        candidates: list[Candidate],
        local_context: str,
        ask_user: AskUser,
    ) -> tuple[str, Candidate | None]:
        while True:
            raw_answer = ask_user(ambiguity, candidates)
            value, selected = resolve_answer(raw_answer, candidates)
            if selected is not None:
                problem = self._candidate_semantic_problem(ambiguity, selected)
                if problem is None:
                    return value, selected
                self.progress(f"所选候选未能解决当前歧义：{problem}")
                continue

            assessment = self._step(
                "正在调用 ChatAnywhere 校验自定义回答",
                lambda: self.chat.generate(
                    AnswerAssessment,
                    VALIDATE_CUSTOM_ANSWER_SYSTEM,
                    f"原始需求：{description}\n\n"
                    f"领域与场景：\n{context.model_dump_json(indent=2)}\n\n"
                    f"当前歧义：\n{ambiguity.model_dump_json(indent=2)}\n\n"
                    f"用户自定义回答：{value}\n\n"
                    f"相关本地知识：\n{local_context or '无'}\n\n"
                    f"已有候选项：\n{_json([item.model_dump(mode='json') for item in candidates])}",
                ),
            )
            if assessment.resolves_ambiguity and assessment.normalized_answer:
                invalid_reason = self._normalized_answer_problem(
                    ambiguity, assessment.normalized_answer
                )
                if invalid_reason is None:
                    self.progress(f"自定义回答有效，规范化为：{assessment.normalized_answer}")
                    return assessment.normalized_answer, None
                assessment = assessment.model_copy(
                    update={
                        "resolves_ambiguity": False,
                        "normalized_answer": None,
                        "reason": invalid_reason,
                        "follow_up_question": ambiguity.question,
                    }
                )

            self.progress(f"自定义回答未能解决当前歧义：{assessment.reason}")
            if assessment.follow_up_question:
                self.progress(f"请补充：{assessment.follow_up_question}")

    def _normalized_answer_problem(
        self, ambiguity: Ambiguity, normalized_answer: str
    ) -> str | None:
        if ambiguity.category not in {"scope", "time"} and re.search(
            r"\b(always|eventually|until|historically|once|since)\b",
            normalized_answer,
            flags=re.IGNORECASE,
        ):
            return "规范化结果擅自加入了时序算子，没有只回答当前歧义"

        identifiers = set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", normalized_answer))
        allowed_words = {
            "km", "h", "m", "s", "true", "false", "and", "or", "not",
        }
        signal_like = {
            item
            for item in identifiers
            if "_" in item and item.lower() not in allowed_words
        }
        unknown = signal_like - self.knowledge.signal_names()
        if unknown:
            return f"规范化结果引入了知识库中不存在的信号：{', '.join(sorted(unknown))}"
        return None

    def _external_candidates(
        self,
        description: str,
        context: DomainContext,
        ambiguity: Ambiguity,
        local_context: str,
        local_source_ids: list[str],
    ) -> list[Candidate]:
        search_query = self._build_search_query(description, context, ambiguity)
        self.progress(f"2/4 本地知识不足，正在使用 Tavily 检索：{search_query}")
        started = time.monotonic()
        web_results = self.tavily.search(search_query)
        self.progress(f"2/4 Tavily 检索完成，用时 {time.monotonic() - started:.1f} 秒")
        web_results = self._select_relevant_web_results(context, ambiguity, web_results)
        result = self._step(
            "3/4 正在调用 ChatAnywhere 生成候选项",
            lambda: self.chat.generate(
                CandidateSet,
                WEB_CANDIDATES_SYSTEM,
                f"待澄清问题：\n{ambiguity.model_dump_json(indent=2)}\n\n"
                f"领域与场景：\n{context.model_dump_json(indent=2)}\n\n"
                f"本地知识：\n{local_context or '无'}\n\n"
                f"Tavily 搜索结果：\n{_json([item.model_dump(mode='json') for item in web_results])}",
            ),
        )
        candidates = sanitize_candidates(
            result.candidates,
            set(local_source_ids),
            {item.url for item in web_results},
        )
        candidates, rejected = executable_candidates(
            ambiguity, candidates, self.knowledge.signal_names()
        )
        if rejected:
            self.progress(f"已拒绝不可执行的搜索候选：{'；'.join(rejected)}")
        if len(candidates) >= 2:
            return candidates

        inference = self._step(
            "相关搜索证据不足，正在调用 ChatAnywhere 生成工程推断候选",
            lambda: self.chat.generate(
                CandidateSet,
                LLM_INFERENCE_CANDIDATES_SYSTEM,
                f"领域与场景：\n{context.model_dump_json(indent=2)}\n\n"
                f"当前歧义：\n{ambiguity.model_dump_json(indent=2)}\n\n"
                f"可用信号知识：\n{local_context or '无'}",
            ),
        )
        inferred = sanitize_candidates(inference.candidates, set(local_source_ids), set())
        inferred, rejected = executable_candidates(
            ambiguity, inferred, self.knowledge.signal_names()
        )
        combined = self._merge_candidates(candidates, inferred)
        if len(combined) < 2:
            fallbacks = self._deterministic_parameterized_fallbacks(
                context, ambiguity, local_source_ids
            )
            combined = self._merge_candidates(combined, fallbacks)
            self.progress("模型候选不足，已补充明确的参数化工程候选，流程继续执行")
        return combined[:3]

    def _review_and_regenerate_candidates(
        self,
        description: str,
        context: DomainContext,
        ambiguity: Ambiguity,
        candidates: list[Candidate],
        local_context: str,
        local_source_ids: list[str],
    ) -> list[Candidate]:
        current = candidates
        accepted: list[Candidate] = []
        rejection_history: list[str] = []
        for round_number in range(1, 4):
            accepted, rejected = self._review_candidates(
                description, context, ambiguity, current, local_context
            )
            rejection_history.extend(rejected)
            if len(accepted) >= 2:
                return accepted[:3]
            if round_number == 3:
                break
            self.progress(
                f"候选审核后不足 2 个，正在根据拒绝原因重新生成（{round_number}/2）"
            )
            regenerated = self._step(
                "正在调用 ChatAnywhere 重新生成匹配当前问题的候选项",
                lambda: self.chat.generate(
                    CandidateSet,
                    LLM_INFERENCE_CANDIDATES_SYSTEM,
                    f"原始需求：{description}\n\n"
                    f"领域与场景：\n{context.model_dump_json(indent=2)}\n\n"
                    f"当前唯一歧义：\n{ambiguity.model_dump_json(indent=2)}\n\n"
                    f"可用信号知识：\n{local_context or '无'}\n\n"
                    f"上一轮候选被拒绝的原因：\n{_json(rejection_history)}\n\n"
                    "请只生成直接回答当前唯一歧义的新候选，不要回答其他问题。",
                ),
            )
            current = sanitize_candidates(
                regenerated.candidates, set(local_source_ids), set()
            )

        fallbacks = self._deterministic_parameterized_fallbacks(
            context, ambiguity, local_source_ids
        )
        fallback_valid, fallback_rejected = self._rule_review_candidates(
            ambiguity, fallbacks
        )
        rejection_history.extend(fallback_rejected)
        combined = self._merge_candidates(accepted, fallback_valid)
        if not combined:
            raise RuntimeError(
                "候选审核连续 3 轮未得到可回答当前问题的候选："
                + "；".join(rejection_history[-5:])
            )
        self.progress("候选审核后已使用与当前问题匹配的参数化候选兜底")
        return combined[:3]

    def _review_candidates(
        self,
        description: str,
        context: DomainContext,
        ambiguity: Ambiguity,
        candidates: list[Candidate],
        local_context: str,
    ) -> tuple[list[Candidate], list[str]]:
        rule_valid, rejected = self._rule_review_candidates(ambiguity, candidates)
        if not rule_valid:
            return [], rejected
        review = self._step(
            "正在调用 ChatAnywhere 审核候选项是否回答当前问题",
            lambda: self.chat.generate(
                CandidateReviewSet,
                CANDIDATE_REVIEW_SYSTEM,
                f"原始需求：{description}\n\n"
                f"领域与场景：\n{context.model_dump_json(indent=2)}\n\n"
                f"当前唯一歧义：\n{ambiguity.model_dump_json(indent=2)}\n\n"
                f"本地知识：\n{local_context or '无'}\n\n"
                f"待审核候选：\n{_json([item.model_dump(mode='json') for item in rule_valid])}",
            ),
        )
        by_id = {item.id: item for item in rule_valid}
        accepted: list[Candidate] = []
        reviewed_ids: set[str] = set()
        for item in review.reviews:
            original = by_id.get(item.candidate_id)
            if original is None or item.candidate_id in reviewed_ids:
                continue
            reviewed_ids.add(item.candidate_id)
            if not item.accepted:
                rejected.append(f"{item.candidate_id}: {item.reason}")
                continue
            candidate = item.normalized_candidate or original
            candidate = candidate.model_copy(
                update={
                    "id": original.id,
                    "source_type": original.source_type,
                    "source_reference": original.source_reference,
                }
            )
            normalized_valid, normalized_rejected = self._rule_review_candidates(
                ambiguity, [candidate]
            )
            accepted.extend(normalized_valid)
            rejected.extend(normalized_rejected)
        for candidate_id in by_id.keys() - reviewed_ids:
            rejected.append(f"{candidate_id}: 审核模型未返回该候选的审核结果")
        if rejected:
            self.progress(f"候选审核已拒绝：{'；'.join(rejected)}")
        return accepted, rejected

    def _rule_review_candidates(
        self, ambiguity: Ambiguity, candidates: list[Candidate]
    ) -> tuple[list[Candidate], list[str]]:
        known_signals = self.knowledge.signal_names()
        normalized = [
            candidate.model_copy(
                update={
                    "parameters": [
                        item for item in candidate.parameters if item not in known_signals
                    ]
                }
            )
            for candidate in candidates
        ]
        executable, rejected = executable_candidates(
            ambiguity, normalized, known_signals
        )
        accepted: list[Candidate] = []
        for candidate in executable:
            problem = self._candidate_semantic_problem(ambiguity, candidate)
            if problem:
                rejected.append(f"{candidate.id}: {problem}")
            else:
                accepted.append(candidate)
        return accepted, rejected

    @staticmethod
    def _candidate_semantic_problem(
        ambiguity: Ambiguity, candidate: Candidate
    ) -> str | None:
        question = f"{ambiguity.id} {ambiguity.description} {ambiguity.question}".lower()
        value = candidate.value.lower()
        combined = f"{value} {candidate.explanation.lower()}"

        if "安全距离" in question or "safe_distance" in question:
            if re.search(r"\b(?:brake_active|aeb_active)\b\s*(?:==|=)", value):
                return "安全距离问题不能用刹车动作或触发公式回答"
            if not any(
                token in combined
                for token in (
                    "front_vehicle_distance",
                    "headway_time",
                    "ttc",
                    "距离",
                    "车头时距",
                )
            ):
                return "候选没有定义距离、车头时距或 TTC 安全判据"

        if ambiguity.id == "define_braking_trigger" or any(
            token in question for token in ("必要的时候", "触发条件", "刹车时机")
        ):
            if "eventually" in value or "响应时间" in combined or "时限" in combined:
                return "刹车触发问题不能用响应时限回答"
            has_condition = bool(
                re.search(r"<=|>=|<|>|==|!=|\bwhen\b|\band\b|&&", value)
            )
            if not has_condition:
                return "候选没有给出可计算的刹车触发谓词"
            if re.fullmatch(r"\s*[a-z_][a-z0-9_]*\s*=\s*[^=]+\s*", value):
                return "候选只定义了阈值，没有定义刹车触发条件"

        if ambiguity.id == "define_braking_response_deadline" or any(
            token in question for token in ("及时刹车", "响应时限", "多长时间")
        ):
            if re.search(r"\balways\s*\[", value):
                return "always[0,T] 表示持续成立，不能表示在 T 内完成响应"
            eventual = bool(re.search(r"eventually\s*\[\s*0\s*,", value))
            time_value = bool(
                re.search(r"\d+(?:\.\d+)?\s*(?:ms|毫秒|s|秒)\b", value)
            )
            time_parameter = bool(
                re.search(r"(?:response|deadline|t_brake|t_aeb|time)", combined)
            )
            if not (eventual or time_value or time_parameter):
                return "响应时限候选缺少时间单位或参数化时间上界"
            if re.search(r"km/h|m/s|启用|最长保持|持续时间", combined):
                return "候选描述的是车速、功能启用条件或保持时间，不是刹车响应时限"
        return None

    @staticmethod
    def _merge_candidates(*groups: list[Candidate]) -> list[Candidate]:
        merged: list[Candidate] = []
        seen: set[str] = set()
        for group in groups:
            for candidate in group:
                if candidate.value in seen:
                    continue
                seen.add(candidate.value)
                merged.append(candidate)
        return merged

    def _deterministic_parameterized_fallbacks(
        self,
        context: DomainContext,
        ambiguity: Ambiguity,
        local_source_ids: list[str],
    ) -> list[Candidate]:
        available = {
            source.rsplit("/", 1)[-1]: source
            for source in local_source_ids
            if source.startswith("signals_kb.txt#")
        }
        result: list[Candidate] = []

        if ambiguity.id == "define_safe_distance" or "安全距离" in ambiguity.description:
            if "front_vehicle_distance" in available:
                result.append(
                    Candidate(
                        id="parameterized_safe_distance",
                        candidate_type="parameterized",
                        value="front_vehicle_distance >= d_safe",
                        explanation="使用可配置的最小安全距离参数，参数单位为 m；具体值需由项目标定。",
                        parameters=["d_safe"],
                        source_type=SourceType.LLM_INFERENCE,
                        source_reference="LLM 工程推断；信号定义来自本地知识库",
                    )
                )
            if "ttc" in available:
                result.append(
                    Candidate(
                        id="parameterized_safe_ttc",
                        candidate_type="parameterized",
                        value="ttc >= ttc_safe",
                        explanation="使用碰撞时间作为动态安全判据，参数单位为 s；具体值需由项目标定。",
                        parameters=["ttc_safe"],
                        source_type=SourceType.LLM_INFERENCE,
                        source_reference="LLM 工程推断；ttc 定义来自本地知识库",
                    )
                )

        if ambiguity.id == "define_braking_trigger" or "触发" in ambiguity.description:
            if "ttc" in available:
                result.append(
                    Candidate(
                        id="parameterized_ttc_trigger",
                        candidate_type="parameterized",
                        value="ttc <= ttc_brake",
                        explanation="当 TTC 低于制动触发参数时请求制动，参数单位为 s。",
                        parameters=["ttc_brake"],
                        source_type=SourceType.LLM_INFERENCE,
                        source_reference="LLM 工程推断；ttc 定义来自本地知识库",
                    )
                )
            if {"front_vehicle_distance", "front_vehicle_closing_speed"} <= available.keys():
                result.append(
                    Candidate(
                        id="parameterized_distance_closing_trigger",
                        candidate_type="parameterized",
                        value="front_vehicle_distance <= d_brake && front_vehicle_closing_speed > 0",
                        explanation="距离低于制动阈值且车辆正在接近时触发，d_brake 单位为 m。",
                        parameters=["d_brake"],
                        source_type=SourceType.LLM_INFERENCE,
                        source_reference="LLM 工程推断；距离和闭合速度来自本地知识库",
                    )
                )

        if ambiguity.id == "define_braking_response_deadline" or "响应时限" in ambiguity.description:
            if "brake_active" in available:
                result.append(
                    Candidate(
                        id="parameterized_brake_response",
                        candidate_type="parameterized",
                        value="eventually[0,t_brake](brake_active == 1)",
                        explanation="要求在参数化响应时限内发出制动请求，t_brake 单位为 s。",
                        parameters=["t_brake"],
                        source_type=SourceType.LLM_INFERENCE,
                        source_reference="LLM 工程推断；brake_active 来自本地知识库",
                    )
                )
            if "aeb_active" in available:
                result.append(
                    Candidate(
                        id="parameterized_aeb_response",
                        candidate_type="parameterized",
                        value="eventually[0,t_aeb](aeb_active == 1)",
                        explanation="要求 AEB 在参数化时限内介入，t_aeb 单位为 s。",
                        parameters=["t_aeb"],
                        source_type=SourceType.LLM_INFERENCE,
                        source_reference="LLM 工程推断；aeb_active 来自本地知识库",
                    )
                )

        available_names = list(available)
        first_signal = available_names[0] if available_names else "metric"
        second_signal = available_names[1] if len(available_names) > 1 else first_signal
        generic = [
            Candidate(
                id="custom_parameter_rule",
                candidate_type="parameterized",
                value=f"{first_signal} <= threshold_param",
                explanation="使用命名参数保留待标定阈值，不自动猜测数值。",
                parameters=["threshold_param"],
                source_type=SourceType.LLM_INFERENCE,
                source_reference="LLM 工程推断",
            ),
            Candidate(
                id="custom_formula_rule",
                candidate_type="parameterized",
                value=f"{second_signal} >= metric_param",
                explanation="使用项目定义的指标和命名参数表达约束。",
                parameters=["metric_param"],
                source_type=SourceType.LLM_INFERENCE,
                source_reference="LLM 工程推断",
            ),
        ]
        return result if len(result) >= 2 else [*result, *generic]

    @staticmethod
    def _build_search_query(
        description: str, context: DomainContext, ambiguity: Ambiguity
    ) -> str:
        parts = [
            context.domain,
            context.scene,
            context.subject,
            *context.quantities,
            *context.expected_units,
            *context.search_keywords,
            ambiguity.knowledge_query,
            description,
        ]
        return " ".join(dict.fromkeys(part.strip() for part in parts if part.strip()))

    def _select_relevant_web_results(
        self,
        context: DomainContext,
        ambiguity: Ambiguity,
        results: list[SearchResult],
    ) -> list[SearchResult]:
        if not results:
            return []
        assessment = self._step(
            "正在调用 ChatAnywhere 判断搜索结果的领域与场景相关性",
            lambda: self.chat.generate(
                SearchRelevanceAssessment,
                ASSESS_SEARCH_RELEVANCE_SYSTEM,
                f"领域与场景：\n{context.model_dump_json(indent=2)}\n\n"
                f"当前歧义：\n{ambiguity.model_dump_json(indent=2)}\n\n"
                f"搜索结果：\n{_json([item.model_dump(mode='json') for item in results])}",
            ),
        )
        existing = {item.url for item in results}
        selected = set(assessment.relevant_urls) & existing
        self.progress(
            f"搜索结果相关性判定：保留 {len(selected)}/{len(results)} 条；{assessment.reason}"
        )
        return [item for item in results if item.url in selected]

    def _step(self, label: str, action):
        self.progress(label)
        started = time.monotonic()
        result = action()
        self.progress(f"{label.split(' 正在')[0]} 完成，用时 {time.monotonic() - started:.1f} 秒")
        return result


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
