from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal, TypedDict

from pydantic import BaseModel, Field, model_validator


class SourceType(StrEnum):
    SIGNAL_KNOWLEDGE = "signal_knowledge"
    STL_KNOWLEDGE = "stl_knowledge"
    TAVILY = "tavily"
    LLM_INFERENCE = "llm_inference"
    USER_INPUT = "user_input"


class Ambiguity(BaseModel):
    id: str = Field(description="Stable short snake_case identifier")
    issue_type: Literal["vagueness", "ambiguity"] = "ambiguity"
    description: str
    question: str
    category: Literal["signal", "threshold", "scope", "time", "operator", "other"]
    knowledge_query: str


class DomainContext(BaseModel):
    domain: str = Field(description="需求所属领域，例如自动驾驶、网络设备、工业控制")
    scene: str = Field(description="领域内的具体场景")
    subject: str = Field(description="被约束的主体或系统")
    quantities: list[str] = Field(default_factory=list, description="相关物理量或状态量")
    expected_units: list[str] = Field(default_factory=list, description="预期单位；无单位则为空")
    search_keywords: list[str] = Field(default_factory=list, description="用于外部检索的领域关键词")
    knowledge_scenes: list[str] = Field(
        default_factory=list,
        description="与本地知识库对应的场景名，例如 AEB、ACC、Parking、Speed_Limit",
    )


class AmbiguityAnalysis(BaseModel):
    context: DomainContext
    ambiguities: list[Ambiguity]


class Candidate(BaseModel):
    id: str
    candidate_type: Literal["numeric", "formula", "parameterized"] = "formula"
    value: str
    explanation: str
    parameters: list[str] = Field(default_factory=list)
    source_type: SourceType
    source_reference: str

    @model_validator(mode="before")
    @classmethod
    def normalize_candidate_type(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        valid_types = {"numeric", "formula", "parameterized"}
        if value.get("candidate_type") in valid_types:
            return value

        normalized = dict(value)
        candidate_value = str(normalized.get("value", "")).strip()
        parameters = normalized.get("parameters") or []
        if parameters:
            candidate_type = "parameterized"
        elif re.fullmatch(
            r"[-+]?\d+(?:\.\d+)?\s*(?:km/h|m/s|ms|s|m|%)?",
            candidate_value,
            flags=re.IGNORECASE,
        ):
            candidate_type = "numeric"
        else:
            candidate_type = "formula"
        normalized["candidate_type"] = candidate_type
        return normalized


class CandidateAssessment(BaseModel):
    local_knowledge_sufficient: bool
    search_query: str | None = None
    candidates: list[Candidate] = Field(default_factory=list, min_length=0, max_length=3)


class CandidateSet(BaseModel):
    candidates: list[Candidate] = Field(min_length=2, max_length=3)


class Clarification(BaseModel):
    ambiguity_id: str
    ambiguity_description: str = ""
    issue_type: Literal["vagueness", "ambiguity"] = "ambiguity"
    category: Literal["signal", "threshold", "scope", "time", "operator", "other"]
    question: str
    answer: str
    selected_candidate_id: str | None = None
    source_type: SourceType
    source_reference: str


class AnswerAssessment(BaseModel):
    resolves_ambiguity: bool
    normalized_answer: str | None = None
    reason: str
    follow_up_question: str | None = None


class SearchResult(BaseModel):
    title: str
    url: str
    content: str


class SearchRelevanceAssessment(BaseModel):
    relevant_urls: list[str] = Field(default_factory=list)
    reason: str


class TranslationFragment(BaseModel):
    nl_fragment: str
    stl_fragment: str


class STLResult(BaseModel):
    clarified_description: str
    formula: str
    explanation: str
    signals_used: list[str]
    assumptions: list[str] = Field(default_factory=list)
    fragment_mappings: list[TranslationFragment] = Field(default_factory=list)


class GraphState(TypedDict, total=False):
    original_text: str
    ambiguities: list[dict]
    current_ambiguity: dict | None
    candidates: list[dict]
    clarifications: list[dict]
    local_context: str
    local_source_ids: list[str]
    search_required: bool
    search_query: str | None
    web_results: list[dict]
    pending_answer: str | dict | None
    final_result: dict | None
    validation_errors: list[str]
    generation_attempts: int
