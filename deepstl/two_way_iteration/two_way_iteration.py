from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator


SCRIPT_DIR = Path(__file__).resolve().parent
DEEPSTL_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = DEEPSTL_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from AST2STL import ast2stl  # noqa: E402


LLM1_MODEL = "deepseek-v4-pro"
LLM2_MODEL = "deepseek-v4-pro"
LLM3_MODEL = "deepseek-v4-pro"

# The initial candidate is not a semantic refinement. If it is inconsistent,
# LLM1 may receive LLM3's feedback and regenerate at most this many times.
MAX_SEMANTIC_REFINEMENTS = 5

# AST/schema repair attempts do not count as semantic refinements because they
# do not produce an STL/NL_2 candidate that can be compared.
MAX_AST_ATTEMPTS = 5
MAX_STRUCTURED_OUTPUT_ATTEMPTS = 3
MAX_WORKERS = 4
MAX_API_ATTEMPTS = 5
API_RETRY_BASE_SECONDS = 2.0
TARGET_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
WORKER_LOCAL = threading.local()
PRINT_LOCK = threading.Lock()

INPUT_CSV = PROJECT_ROOT / "dataset/deepstl_test_300_sample.csv"
SCHEMA_FILE = PROJECT_ROOT / "knowledge_base/ast_schema.txt"
OPERATOR_KNOWLEDGE_FILE = PROJECT_ROOT / "knowledge_base/stl_operators.md"
TEMPLATE_OPERATOR_KNOWLEDGE_FILE = PROJECT_ROOT / "knowledge_base/template_operator_knowledge.md"
OUTPUT_FILE = PROJECT_ROOT / "result/two_way_iteration_deepseek_v4_pro_result.txt"
FAIL_TIMES_FILE = PROJECT_ROOT / "tmp/two_way_iteration_fail_times.txt"
TRACE_FILE = PROJECT_ROOT / "result/ast_intermediate/two_way_iteration.jsonl"


def extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("schema file does not contain a JSON object")
    return text[start : end + 1]


def load_schema() -> tuple[str, Draft202012Validator]:
    schema_text = extract_json(SCHEMA_FILE.read_text(encoding="utf-8"))
    schema = json.loads(schema_text)
    Draft202012Validator.check_schema(schema)
    return schema_text, Draft202012Validator(schema)


def load_operator_knowledge() -> str:
    return OPERATOR_KNOWLEDGE_FILE.read_text(encoding="utf-8").strip()


def load_template_operator_knowledge() -> str:
    return TEMPLATE_OPERATOR_KNOWLEDGE_FILE.read_text(encoding="utf-8").strip()


def build_llm1_system_prompt(
    schema_text: str,
    operator_knowledge: str,
    template_operator_knowledge: str,
) -> str:
    return f"""You are LLM1. Convert a natural-language STL requirement into AST JSON.

Output requirements:
- Return exactly one JSON object.
- The JSON object must be the AST root node itself.
- Do not wrap the AST in keys such as "ast", "result", or "schema".
- Do not output markdown, code fences, comments, explanations, or STL text.
- The JSON object must validate against the following JSON Schema.
- Use only operators and fields allowed by this JSON Schema.
- Use the train operator knowledge and template operator knowledge only as semantic guidance.
- If the knowledge conflicts with the JSON Schema, the JSON Schema takes precedence.
- Use operator names exactly as specified by the JSON Schema enum values.
- Preserve every identifier, threshold, comparison direction, Boolean relationship, temporal
  interval, interval boundary, operand order, negation scope, and nesting relationship expressed
  by the requirement.
- Signal and parameter names must be plain identifiers matching ^[A-Za-z_][A-Za-z0-9_]*$. Never
  invent function-like names such as mode(sig1); phrases such as "the mode of signal sig1" still
  refer to the dataset signal identifier sig1.
- Every explicit finite interval must have numeric endpoints and must be closed at both ends.
  Generate [a:b], never (a:b), (a:b], or [a:b). The lower endpoint must not exceed the upper.
- The only unbounded interval is lower=0, upper="inf", lowerInclusive=true, and
  upperInclusive=false. Phrases such as "in the future before the simulation ends" or "until the
  end" use this canonical unbounded interval on the finite trace. Never invent symbolic endpoints
  such as sim_end, simulation_end, sim_len, or simulation_duration.
- When semantic feedback from a previous candidate is supplied, correct every reported mismatch
  while continuing to translate the original requirement. Do not copy the reverse translation as
  if it were the target requirement, and do not change semantics that the feedback did not reject.

JSON Schema:
{schema_text}

Train operator knowledge:
{operator_knowledge}

Template operator knowledge:
{template_operator_knowledge}
"""


def build_llm1_user_prompt(
    nl_1: str,
    semantic_feedback: dict[str, Any] | None = None,
    validation_error: str | None = None,
    previous_output: str | None = None,
) -> str:
    prompt = f"""Generate the AST JSON object for the following natural-language requirement.

Original natural-language requirement (NL_1):
{nl_1}
"""
    if semantic_feedback is not None:
        prompt += f"""

The previous valid STL candidate was semantically inconsistent with NL_1. Use the following
feedback as correction evidence and regenerate the complete AST from NL_1:
{json.dumps(semantic_feedback, ensure_ascii=False, indent=2)}
"""
    if validation_error is not None:
        prompt += f"""

Your previous output did not produce a valid AST/STL candidate.

Validation or conversion error:
{validation_error}

Previous output:
{previous_output}

Regenerate one complete valid AST JSON object only.
"""
    return prompt


def build_llm2_system_prompt() -> str:
    return """You are LLM2, a meticulous STL-to-natural-language semantic translator.

Your only task is to translate the received STL formula into NL_2 whose semantics are exactly the
same as the complete STL formula. Semantic fidelity and completeness are more important than
brevity, elegance, or natural phrasing. A long or repetitive translation is acceptable.

Mandatory translation rules:
1. Parse the entire formula recursively according to its parentheses, operator precedence, and
   operand order. Translate the root formula and every nested subformula; omit nothing.
2. Preserve every signal/parameter name and every numeric constant exactly. Explicitly
   state arithmetic expressions and the exact comparison relation (<, <=, >, >=, ==).
3. Explicitly state every Boolean operator (not, and, or, implication ->, equivalence <->), all of
   its operands, and the exact scope of negation and grouping. Do not replace implication or
   equivalence with a merely similar relationship.
4. Fully state the semantics of every future operator (always, eventually, until) and every past
   operator (historically, once, since). For binary temporal operators,
   preserve which subformula is left and which is right and explain their full relationship.
5. State every explicit numeric time interval exactly. The target formulas use closed finite
   intervals [a:b], inclusive at both endpoints. An omitted interval means that the formula has no
   explicit numeric bound; when evaluated on a finite simulation trace, its scope extends through
   the remaining trace up to its end, rather than beyond the available trace.
6. Fully state edge semantics for rise and fall, including their complete operand and scope.
7. Preserve temporal and Boolean nesting literally. Do not flatten nested operators, exchange
   operands, apply algebraic/logical simplifications, infer unstated domain knowledge, or add a
   condition absent from the formula.
8. Do not summarize the formula. Before answering, silently walk through the formula token by token
   and verify that every atomic predicate, operator, interval, boundary, operand, and scope has an
   explicit counterpart in NL_2.

Output requirements:
- Return exactly one JSON object with exactly one key named "nl_2".
- The value of "nl_2" must be one self-contained, unambiguous, complete natural-language semantic
  description of the whole formula.
- Do not output the STL itself, markdown, code fences, comments, or any additional keys.
"""


def build_llm2_user_prompt(stl: str) -> str:
    return f"""Translate this complete STL formula into a semantically identical and exhaustive
natural-language description. Do not shorten or summarize it.

STL formula:
{stl}
"""


def build_llm3_compare_system_prompt() -> str:
    return """You are LLM3, a strict semantic-equivalence judge.

Compare NL_1 with NL_2. NL_2 is intended to be a complete natural-language rendering of an STL
formula. Judge semantic equivalence, not wording similarity.

Apply these project-specific finite-trace conventions while judging:
- An unbounded always/eventually operator is evaluated only over the available finite trace. Natural
  language such as "in the future before the simulation ends", "until the simulation ends", or
  "through the end" therefore does not require an explicit simulation_end interval endpoint.
- Explicit finite intervals have numeric endpoints and are closed. Dataset phrases such as
  "within/subsequent/following N time units" map to [0:N], not (0:N], and a phrase like "within A
  to B" maps to [A:B]. Do not report missing strict endpoint exclusions as a mismatch.
- Phrases such as "the mode of signal sig1" identify sig1; they do not introduce a function or a
  new identifier named mode(sig1).
- Never request symbolic interval endpoints, open/half-open finite intervals, function-like signal
  names, or operators absent from the supplied STL target language in semantic feedback.

Set consistent=true only when the two descriptions impose exactly the same requirement. Check at
least: identifiers; arithmetic expressions; constants and thresholds; comparison directions;
Boolean operators; implication direction; negation scope; temporal operators; past versus future;
time bounds and interval endpoints; operand order; trigger/consequence roles; nesting; rise/fall
edge semantics; and whether either side adds or omits any condition. Do not use
background knowledge to repair an ambiguity or treat one-way implication as equivalence. If one
description is stronger, weaker, broader, narrower, or underspecified relative to the other, mark
it inconsistent.

For nested not/and/or expressions, recursively preserve the complete operator tree before deciding.
Do not silently drop a branch, replace and with or, or make an invalid De Morgan transformation.

The similarity_score is an integer from 0 to 100 used only to rank inconsistent candidates. It must
not make the equivalence decision lenient.

Output exactly one JSON object with this shape:
{
  "consistent": true or false,
  "similarity_score": integer from 0 to 100,
  "inconsistencies": [
    {
      "aspect": "short category",
      "nl_1_semantics": "what NL_1 requires for this aspect",
      "nl_2_semantics": "what NL_2 says for this aspect",
      "explanation": "precise semantic difference"
    }
  ],
  "reason": "overall judgment"
}

When consistent=true, inconsistencies must be empty. When consistent=false, list every detected
semantic mismatch and do not return an empty inconsistencies array. Do not output markdown, code
fences, comments, or additional keys.
"""


def build_llm3_compare_user_prompt(nl_1: str, nl_2: str) -> str:
    return f"""Strictly compare the semantics of these two requirements.

NL_1:
{nl_1}

NL_2:
{nl_2}
"""


def build_llm3_select_system_prompt() -> str:
    return """You are LLM3 performing final candidate selection after semantic refinement was
exhausted. Select the single candidate whose NL_2 is semantically closest to NL_1. Judge actual
requirement semantics rather than wording, and prioritize preservation of operators, operand order,
identifiers, thresholds, Boolean scope, temporal scope, time bounds, and nesting. Use the earlier
comparison records as evidence but independently verify the choice.

Use the same project conventions as the comparison stage: unbounded temporal operators range over
the remaining finite trace, phrases about the simulation ending do not require a symbolic endpoint,
explicit numeric intervals are closed, and mode-of-signal wording does not create a mode(...) name.

Return exactly one JSON object with exactly these keys:
{
  "selected_candidate_id": positive integer,
  "reason": "precise reason this candidate has the smallest semantic mismatch"
}

Do not output markdown, code fences, comments, or additional keys.
"""


def build_llm3_select_user_prompt(nl_1: str, candidates: list[dict[str, Any]]) -> str:
    selection_view = [
        {
            "candidate_id": candidate["candidate_id"],
            "stl": candidate["stl"],
            "nl_2": candidate["nl_2"],
            "comparison": candidate["comparison"],
        }
        for candidate in candidates
    ]
    return f"""Select the candidate semantically closest to NL_1.

NL_1:
{nl_1}

Candidates:
{json.dumps(selection_view, ensure_ascii=False, indent=2)}
"""


def make_client() -> Any:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ModuleNotFoundError:
        pass

    from openai import OpenAI

    return OpenAI()


class LLMAPIError(RuntimeError):
    def __init__(self, message: str, retry_times: int) -> None:
        super().__init__(message)
        self.retry_times = retry_times


def is_retryable_api_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {408, 409, 429}:
        return True
    if isinstance(status_code, int) and status_code >= 500:
        return True
    return type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "RateLimitError",
    }


def get_worker_client() -> Any:
    client = getattr(WORKER_LOCAL, "client", None)
    if client is None:
        client = make_client()
        WORKER_LOCAL.client = client
    return client


def call_llm(
    client: Any,
    model: str,
    system_prompt: str,
    user_prompt: str,
    role: str,
) -> tuple[str, int]:
    api_retry_times = 0
    response = None
    for api_attempt in range(1, MAX_API_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            break
        except Exception as exc:
            can_retry = is_retryable_api_error(exc) and api_attempt < MAX_API_ATTEMPTS
            if not can_retry:
                raise LLMAPIError(
                    f"{role} API request failed after {api_attempt} attempt(s): "
                    f"{type(exc).__name__}: {exc}",
                    api_retry_times,
                ) from exc

            api_retry_times += 1
            delay = API_RETRY_BASE_SECONDS * (2 ** (api_attempt - 1))
            delay += random.uniform(0, min(1.0, delay * 0.25))
            with PRINT_LOCK:
                print(
                    f"{role} API调用失败，将在{delay:.1f}秒后重试 "
                    f"({api_attempt}/{MAX_API_ATTEMPTS}): {type(exc).__name__}: {exc}"
                )
            time.sleep(delay)

    if response is None:
        raise LLMAPIError(f"{role} API request produced no response", api_retry_times)
    content = response.choices[0].message.content
    if content is None or not content.strip():
        raise ValueError("LLM returned empty content")
    return content.strip(), api_retry_times


def parse_json_object(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("LLM output must be a JSON object")
    return value


def validate_target_ast_constraints(value: Any, path: str = "<root>") -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_target_ast_constraints(item, f"{path}/{index}")
        return
    if not isinstance(value, dict):
        return

    expr_type = value.get("exprType")
    if expr_type in {"signal", "parameter"}:
        name = value.get("name")
        if isinstance(name, str) and TARGET_IDENTIFIER_RE.fullmatch(name) is None:
            raise ValueError(
                f"{path}/name: {expr_type} name {name!r} is not a plain target identifier"
            )
    if expr_type == "constant" and isinstance(value.get("value"), str):
        raise ValueError(f"{path}/value: string constants are not allowed by the target AST")

    interval = value.get("interval")
    if isinstance(interval, dict):
        interval_path = f"{path}/interval"
        lower = interval.get("lower")
        upper = interval.get("upper")
        lower_inclusive = interval.get("lowerInclusive")
        upper_inclusive = interval.get("upperInclusive")

        if isinstance(lower, str) or (isinstance(upper, str) and upper != "inf"):
            raise ValueError(
                f"{interval_path}: symbolic interval endpoints are not allowed; "
                "use numeric endpoints or the canonical [0:inf) interval"
            )
        if upper == "inf":
            if lower != 0 or lower_inclusive is not True or upper_inclusive is not False:
                raise ValueError(
                    f"{interval_path}: an unbounded interval must be exactly [0:inf)"
                )
        elif (
            isinstance(lower, (int, float))
            and not isinstance(lower, bool)
            and isinstance(upper, (int, float))
            and not isinstance(upper, bool)
        ):
            if lower_inclusive is not True or upper_inclusive is not True:
                raise ValueError(f"{interval_path}: finite intervals must be closed [lower:upper]")
            if lower > upper:
                raise ValueError(f"{interval_path}: lower endpoint must not exceed upper endpoint")

    node_type = value.get("nodeType")
    operator = value.get("operator")
    if node_type == "temporal" and operator not in {"always", "eventually", "until"}:
        raise ValueError(f"{path}/operator: unsupported future operator {operator!r}")
    if node_type == "edge":
        if operator not in {"rise", "fall"}:
            raise ValueError(f"{path}/operator: unsupported edge operator {operator!r}")
        if value.get("mode", "strict") != "strict":
            raise ValueError(f"{path}/mode: only strict edge mode is supported")
    if node_type == "statistical":
        raise ValueError(f"{path}/nodeType: statistical formulas are not supported")

    for key, item in value.items():
        validate_target_ast_constraints(item, f"{path}/{key}")


def validate_ast(ast: dict[str, Any], validator: Draft202012Validator) -> None:
    validate_target_ast_constraints(ast)
    errors = sorted(validator.iter_errors(ast), key=lambda item: tuple(map(str, item.absolute_path)))
    if not errors:
        return
    error = errors[0]
    location = "/".join(str(part) for part in error.absolute_path) or "<root>"
    raise ValueError(f"{location}: {error.message}")


def ast_to_stl(ast: dict[str, Any]) -> str:
    return ast2stl(json.dumps(ast, ensure_ascii=False, separators=(",", ":")))


def generate_ast_and_stl(
    client: Any,
    system_prompt: str,
    validator: Draft202012Validator,
    nl_1: str,
    semantic_feedback: dict[str, Any] | None,
) -> tuple[
    dict[str, Any] | None,
    str | None,
    int,
    str | None,
    list[dict[str, Any]],
    int,
]:
    validation_error = None
    previous_output = None
    fail_times = 0
    repair_history: list[dict[str, Any]] = []
    api_retry_times = 0

    for ast_attempt in range(1, MAX_AST_ATTEMPTS + 1):
        output = None
        try:
            output, call_api_retry_times = call_llm(
                client,
                LLM1_MODEL,
                system_prompt,
                build_llm1_user_prompt(
                    nl_1,
                    semantic_feedback,
                    validation_error,
                    previous_output,
                ),
                "LLM1",
            )
            api_retry_times += call_api_retry_times
            previous_output = output
            ast = parse_json_object(output)
            validate_ast(ast, validator)
            stl = ast_to_stl(ast)
            if not stl.strip():
                raise ValueError("AST2STL returned an empty formula")
            return ast, stl, fail_times, None, repair_history, api_retry_times
        except LLMAPIError as exc:
            api_retry_times += exc.retry_times
            validation_error = f"{type(exc).__name__}: {exc}"
            return (
                None,
                None,
                fail_times,
                validation_error,
                repair_history,
                api_retry_times,
            )
        except Exception as exc:  # JSON, schema, and AST2STL failures are repairable here.
            fail_times += 1
            validation_error = f"{type(exc).__name__}: {exc}"
            repair_history.append(
                {
                    "ast_attempt": ast_attempt,
                    "output": output,
                    "error": validation_error,
                }
            )
            previous_output = output

    return None, None, fail_times, validation_error, repair_history, api_retry_times


StructuredValidator = Callable[[dict[str, Any]], None]


def call_structured_role(
    client: Any,
    model: str,
    system_prompt: str,
    user_prompt: str,
    validator: StructuredValidator,
    role: str,
) -> tuple[dict[str, Any] | None, int, str | None, int]:
    error = None
    previous_output = None
    fail_times = 0
    api_retry_times = 0

    for _ in range(MAX_STRUCTURED_OUTPUT_ATTEMPTS):
        repair_prompt = user_prompt
        if error is not None:
            repair_prompt += f"""

Your previous response was invalid.
Error: {error}
Previous response: {previous_output}
Return the complete required JSON object again.
"""
        try:
            output, call_api_retry_times = call_llm(
                client,
                model,
                system_prompt,
                repair_prompt,
                role,
            )
            api_retry_times += call_api_retry_times
            previous_output = output
            value = parse_json_object(output)
            validator(value)
            return value, fail_times, None, api_retry_times
        except LLMAPIError as exc:
            api_retry_times += exc.retry_times
            error = f"{type(exc).__name__}: {exc}"
            return None, fail_times, error, api_retry_times
        except Exception as exc:
            fail_times += 1
            error = f"{type(exc).__name__}: {exc}"

    return None, fail_times, error, api_retry_times


def require_exact_keys(value: dict[str, Any], expected: set[str]) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(f"expected keys {sorted(expected)}, got {sorted(actual)}")


def validate_llm2_output(value: dict[str, Any]) -> None:
    require_exact_keys(value, {"nl_2"})
    if not isinstance(value["nl_2"], str) or not value["nl_2"].strip():
        raise ValueError("nl_2 must be a non-empty string")


def validate_llm3_comparison(value: dict[str, Any]) -> None:
    require_exact_keys(value, {"consistent", "similarity_score", "inconsistencies", "reason"})
    consistent = value["consistent"]
    score = value["similarity_score"]
    inconsistencies = value["inconsistencies"]

    if not isinstance(consistent, bool):
        raise ValueError("consistent must be a boolean")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("similarity_score must be an integer from 0 to 100")
    if not isinstance(value["reason"], str) or not value["reason"].strip():
        raise ValueError("reason must be a non-empty string")
    if not isinstance(inconsistencies, list):
        raise ValueError("inconsistencies must be an array")
    if consistent and inconsistencies:
        raise ValueError("inconsistencies must be empty when consistent is true")
    if not consistent and not inconsistencies:
        raise ValueError("inconsistencies must not be empty when consistent is false")

    expected_item_keys = {"aspect", "nl_1_semantics", "nl_2_semantics", "explanation"}
    for index, item in enumerate(inconsistencies):
        if not isinstance(item, dict):
            raise ValueError(f"inconsistencies[{index}] must be an object")
        require_exact_keys(item, expected_item_keys)
        for key in expected_item_keys:
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError(f"inconsistencies[{index}].{key} must be a non-empty string")


def make_selector_validator(valid_ids: set[int]) -> StructuredValidator:
    def validate(value: dict[str, Any]) -> None:
        require_exact_keys(value, {"selected_candidate_id", "reason"})
        selected_id = value["selected_candidate_id"]
        if isinstance(selected_id, bool) or not isinstance(selected_id, int):
            raise ValueError("selected_candidate_id must be an integer")
        if selected_id not in valid_ids:
            raise ValueError(f"selected_candidate_id must be one of {sorted(valid_ids)}")
        if not isinstance(value["reason"], str) or not value["reason"].strip():
            raise ValueError("reason must be a non-empty string")

    return validate


def make_semantic_feedback(
    nl_1: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "nl_1": nl_1,
        "stl": candidate["stl"],
        "stl_semantics_nl_2": candidate["nl_2"],
        "nl_2_vs_nl_1_inconsistencies": candidate["comparison"]["inconsistencies"],
        "comparison_reason": candidate["comparison"]["reason"],
    }


def fallback_best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        candidates,
        key=lambda candidate: candidate["comparison"]["similarity_score"],
    )


def select_closest_candidate(
    client: Any,
    nl_1: str,
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, int, str | None, int]:
    valid_ids = {candidate["candidate_id"] for candidate in candidates}
    selection, fail_times, error, api_retry_times = call_structured_role(
        client,
        LLM3_MODEL,
        build_llm3_select_system_prompt(),
        build_llm3_select_user_prompt(nl_1, candidates),
        make_selector_validator(valid_ids),
        "LLM3_SELECT",
    )

    if selection is not None:
        selected_id = selection["selected_candidate_id"]
        selected = next(
            candidate for candidate in candidates if candidate["candidate_id"] == selected_id
        )
        return selected, selection["reason"], fail_times, None, api_retry_times

    selected = fallback_best_candidate(candidates)
    reason = (
        "LLM3 final selection failed; used the candidate with the highest prior "
        f"similarity_score ({selected['comparison']['similarity_score']})."
    )
    return selected, reason, fail_times, error, api_retry_times


def process_one(
    llm1_client: Any,
    llm2_client: Any,
    llm3_client: Any,
    llm1_system_prompt: str,
    validator: Draft202012Validator,
    taskid: int,
    nl_1: str,
    gold_stl: str,
) -> dict[str, Any]:
    processing_started = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    comparable_candidates: list[dict[str, Any]] = []
    semantic_feedback = None
    selected_candidate = None
    selection_reason = None
    terminal_error = None
    selector_fail_times = 0
    selector_error = None
    selector_api_retry_times = 0
    selector_elapsed_seconds = 0.0

    max_candidates = 1 + MAX_SEMANTIC_REFINEMENTS
    for candidate_id in range(1, max_candidates + 1):
        semantic_refinement = candidate_id - 1
        attempt: dict[str, Any] = {
            "candidate_id": candidate_id,
            "phase": "initial" if semantic_refinement == 0 else "semantic_refinement",
            "semantic_refinement": semantic_refinement,
            "status": "started",
            "ast": None,
            "stl": None,
            "nl_2": None,
            "comparison": None,
            "llm1_fail_times": 0,
            "llm1_repair_history": [],
            "llm1_api_retry_times": 0,
            "llm1_elapsed_seconds": 0.0,
            "llm2_fail_times": 0,
            "llm2_api_retry_times": 0,
            "llm2_elapsed_seconds": 0.0,
            "llm3_fail_times": 0,
            "llm3_api_retry_times": 0,
            "llm3_elapsed_seconds": 0.0,
            "error": None,
        }
        attempts.append(attempt)

        role_started = time.perf_counter()
        (
            ast,
            stl,
            llm1_fail_times,
            error,
            llm1_repair_history,
            llm1_api_retry_times,
        ) = generate_ast_and_stl(
            llm1_client,
            llm1_system_prompt,
            validator,
            nl_1,
            semantic_feedback,
        )
        attempt["llm1_fail_times"] = llm1_fail_times
        attempt["llm1_repair_history"] = llm1_repair_history
        attempt["llm1_api_retry_times"] = llm1_api_retry_times
        attempt["llm1_elapsed_seconds"] = round(time.perf_counter() - role_started, 3)
        if ast is None or stl is None:
            terminal_error = f"LLM1 failed to produce a valid AST/STL: {error}"
            attempt["status"] = "llm1_failed"
            attempt["error"] = terminal_error
            break
        attempt["ast"] = ast
        attempt["stl"] = stl

        role_started = time.perf_counter()
        llm2_output, llm2_fail_times, error, llm2_api_retry_times = call_structured_role(
            llm2_client,
            LLM2_MODEL,
            build_llm2_system_prompt(),
            build_llm2_user_prompt(stl),
            validate_llm2_output,
            "LLM2",
        )
        attempt["llm2_fail_times"] = llm2_fail_times
        attempt["llm2_api_retry_times"] = llm2_api_retry_times
        attempt["llm2_elapsed_seconds"] = round(time.perf_counter() - role_started, 3)
        if llm2_output is None:
            terminal_error = f"LLM2 failed to produce NL_2: {error}"
            attempt["status"] = "llm2_failed"
            attempt["error"] = terminal_error
            break
        nl_2 = llm2_output["nl_2"].strip()
        attempt["nl_2"] = nl_2

        role_started = time.perf_counter()
        comparison, llm3_fail_times, error, llm3_api_retry_times = call_structured_role(
            llm3_client,
            LLM3_MODEL,
            build_llm3_compare_system_prompt(),
            build_llm3_compare_user_prompt(nl_1, nl_2),
            validate_llm3_comparison,
            "LLM3_COMPARE",
        )
        attempt["llm3_fail_times"] = llm3_fail_times
        attempt["llm3_api_retry_times"] = llm3_api_retry_times
        attempt["llm3_elapsed_seconds"] = round(time.perf_counter() - role_started, 3)
        if comparison is None:
            terminal_error = f"LLM3 failed to compare NL_1 and NL_2: {error}"
            attempt["status"] = "llm3_failed"
            attempt["error"] = terminal_error
            break

        attempt["comparison"] = comparison
        attempt["status"] = "consistent" if comparison["consistent"] else "inconsistent"
        comparable_candidates.append(attempt)

        if comparison["consistent"]:
            selected_candidate = attempt
            selection_reason = (
                f"Candidate {candidate_id} was judged semantically equivalent by LLM3."
            )
            terminal_error = None
            break

        if semantic_refinement < MAX_SEMANTIC_REFINEMENTS:
            semantic_feedback = make_semantic_feedback(nl_1, attempt)

    if selected_candidate is None and comparable_candidates:
        selector_started = time.perf_counter()
        (
            selected_candidate,
            selection_reason,
            selector_fail_times,
            selector_error,
            selector_api_retry_times,
        ) = select_closest_candidate(llm3_client, nl_1, comparable_candidates)
        selector_elapsed_seconds = round(time.perf_counter() - selector_started, 3)

    ast_fail_times_total = sum(attempt["llm1_fail_times"] for attempt in attempts)
    semantic_refinements_used = max(
        (attempt["semantic_refinement"] for attempt in attempts),
        default=0,
    )
    status = "ok" if selected_candidate is not None else "fail"
    semantic_consistent = bool(
        selected_candidate is not None and selected_candidate["comparison"]["consistent"]
    )

    if selected_candidate is None and terminal_error is None:
        terminal_error = "No comparable STL/NL_2 candidate was produced."

    total_api_retry_times = selector_api_retry_times + sum(
        attempt["llm1_api_retry_times"]
        + attempt["llm2_api_retry_times"]
        + attempt["llm3_api_retry_times"]
        for attempt in attempts
    )

    return {
        "taskid": taskid,
        "english": nl_1,
        "gold_stl": gold_stl,
        "status": status,
        "selected_candidate_id": (
            selected_candidate["candidate_id"] if selected_candidate is not None else None
        ),
        "selected_stl": selected_candidate["stl"] if selected_candidate is not None else None,
        "selected_nl_2": selected_candidate["nl_2"] if selected_candidate is not None else None,
        "semantic_consistent": semantic_consistent,
        "semantic_refinements_used": semantic_refinements_used,
        "ast_fail_times_total": ast_fail_times_total,
        "selection_reason": selection_reason,
        "selector_fail_times": selector_fail_times,
        "selector_api_retry_times": selector_api_retry_times,
        "selector_elapsed_seconds": selector_elapsed_seconds,
        "selector_error": selector_error,
        "total_api_retry_times": total_api_retry_times,
        "processing_elapsed_seconds": round(time.perf_counter() - processing_started, 3),
        "error": terminal_error if selected_candidate is None else None,
        "attempts": attempts,
    }


def append_trace(trace_file, record: dict[str, Any]) -> None:
    trace_file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    trace_file.flush()


def append_result(
    out_file,
    taskid: int,
    gold_stl: str,
    pred_stl: str,
    is_first: bool,
) -> None:
    if not is_first:
        out_file.write(",\n")
    out_file.write(
        "  {\n"
        f"    taskid:{taskid},\n"
        f"    gold_stl:{json.dumps(gold_stl, ensure_ascii=False)},\n"
        f"    pred_stl:{json.dumps(pred_stl, ensure_ascii=False)},\n"
        "  }"
    )
    out_file.flush()


def append_fail_times(fail_file, taskid: int, fail_times: int) -> None:
    fail_file.write(f"{taskid}:{fail_times}\n")
    fail_file.flush()


def build_run_signature(llm1_system_prompt: str) -> str:
    signature_parts = [
        "two-way-iteration-parallel-v1",
        LLM1_MODEL,
        LLM2_MODEL,
        LLM3_MODEL,
        str(MAX_SEMANTIC_REFINEMENTS),
        str(MAX_AST_ATTEMPTS),
        str(MAX_STRUCTURED_OUTPUT_ATTEMPTS),
        llm1_system_prompt,
        build_llm2_system_prompt(),
        build_llm3_compare_system_prompt(),
        build_llm3_select_system_prompt(),
        INPUT_CSV.read_text(encoding="utf-8"),
    ]
    digest = hashlib.sha256()
    for part in signature_parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:20]


def load_checkpoint_records(run_signature: str) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    if not TRACE_FILE.exists():
        return records

    with TRACE_FILE.open(encoding="utf-8") as trace_file:
        for line_number, line in enumerate(trace_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                with PRINT_LOCK:
                    print(f"忽略追踪文件第{line_number}行的损坏记录: {exc}")
                continue
            if record.get("run_signature") != run_signature:
                continue
            taskid = record.get("taskid")
            if isinstance(taskid, int):
                records[taskid] = record
    return records


def rewrite_checkpoint(records: dict[int, dict[str, Any]]) -> None:
    with TRACE_FILE.open("w", encoding="utf-8") as trace_file:
        for taskid in sorted(records):
            append_trace(trace_file, records[taskid])


def make_unhandled_failure_record(
    row: dict[str, Any],
    run_signature: str,
    exc: Exception,
    elapsed_seconds: float,
) -> dict[str, Any]:
    return {
        "run_signature": run_signature,
        "taskid": row["taskid"],
        "english": row["english"],
        "gold_stl": row["gold_stl"],
        "status": "fail",
        "selected_candidate_id": None,
        "selected_stl": None,
        "selected_nl_2": None,
        "semantic_consistent": False,
        "semantic_refinements_used": 0,
        "ast_fail_times_total": 0,
        "selection_reason": None,
        "selector_fail_times": 0,
        "selector_api_retry_times": 0,
        "selector_elapsed_seconds": 0.0,
        "selector_error": None,
        "total_api_retry_times": 0,
        "processing_elapsed_seconds": round(elapsed_seconds, 3),
        "error": f"Unhandled worker error: {type(exc).__name__}: {exc}",
        "attempts": [],
    }


def process_work_item(
    work_item: tuple[
        dict[str, Any],
        str,
        Draft202012Validator,
        str,
    ],
) -> dict[str, Any]:
    row, llm1_system_prompt, validator, run_signature = work_item
    started = time.perf_counter()
    try:
        # A thread-local client avoids sharing a connection pool between workers. The three roles
        # remain independent stateless API calls even though they reuse the worker's client.
        client = get_worker_client()
        record = process_one(
            client,
            client,
            client,
            llm1_system_prompt,
            validator,
            row["taskid"],
            row["english"],
            row["gold_stl"],
        )
        record["run_signature"] = run_signature
        return record
    except Exception as exc:
        return make_unhandled_failure_record(
            row,
            run_signature,
            exc,
            time.perf_counter() - started,
        )


def write_final_outputs(
    rows: list[dict[str, Any]],
    records: dict[int, dict[str, Any]],
) -> None:
    with (
        OUTPUT_FILE.open("w", encoding="utf-8") as out_file,
        FAIL_TIMES_FILE.open("w", encoding="utf-8") as fail_file,
    ):
        out_file.write("{\n")
        for index, row in enumerate(rows):
            record = records.get(row["taskid"])
            pred_stl = record.get("selected_stl") if record is not None else None
            fail_times = record.get("ast_fail_times_total", 0) if record is not None else 0
            append_result(
                out_file,
                row["taskid"],
                row["gold_stl"],
                pred_stl or "fail",
                index == 0,
            )
            append_fail_times(fail_file, row["taskid"], fail_times)
        out_file.write("\n}\n")


def main() -> None:
    run_started = time.perf_counter()

    schema_text, validator = load_schema()
    operator_knowledge = load_operator_knowledge()
    template_operator_knowledge = load_template_operator_knowledge()
    llm1_system_prompt = build_llm1_system_prompt(
        schema_text,
        operator_knowledge,
        template_operator_knowledge,
    )
    run_signature = build_run_signature(llm1_system_prompt)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAIL_TIMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with INPUT_CSV.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = [
            {
                "taskid": taskid,
                "english": row["English"],
                "gold_stl": row["STL"],
            }
            for taskid, row in enumerate(reader)
        ]

    records = load_checkpoint_records(run_signature)
    rewrite_checkpoint(records)
    completed_taskids = {
        taskid for taskid, record in records.items() if record.get("status") == "ok"
    }
    pending_rows = [row for row in rows if row["taskid"] not in completed_taskids]

    print(
        f"运行签名={run_signature}, 已恢复={len(completed_taskids)}, "
        f"待处理={len(pending_rows)}, 并发数={MAX_WORKERS}"
    )

    work_items = [
        (row, llm1_system_prompt, validator, run_signature)
        for row in pending_rows
    ]
    with (
        TRACE_FILE.open("a", encoding="utf-8") as trace_file,
        ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="stl-worker") as executor,
    ):
        futures = [executor.submit(process_work_item, work_item) for work_item in work_items]
        for completed_index, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            append_trace(trace_file, record)
            records[record["taskid"]] = record
            print(
                f"第{record['taskid']}条数据已完成 "
                f"({completed_index}/{len(pending_rows)}): status={record['status']}, "
                f"semantic_consistent={record['semantic_consistent']}, "
                f"semantic_refinements={record['semantic_refinements_used']}, "
                f"elapsed={record['processing_elapsed_seconds']:.1f}s"
            )

    write_final_outputs(rows, records)
    ok_count = sum(record.get("status") == "ok" for record in records.values())
    consistent_count = sum(record.get("semantic_consistent") is True for record in records.values())
    api_retries = sum(record.get("total_api_retry_times", 0) for record in records.values())
    print(
        f"全部完成: ok={ok_count}/{len(rows)}, semantic_consistent={consistent_count}/{len(rows)}, "
        f"api_retries={api_retries}, wall_time={time.perf_counter() - run_started:.1f}s"
    )


if __name__ == "__main__":
    main()
