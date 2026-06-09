#!/usr/bin/env python3
"""Validate one STL/NL candidate with one independent Responses API call."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "scene",
    "template",
    "stl",
    "signals_info",
    "numeric_rationale",
    "operator_semantics",
    "translations",
}

TRANSLATION_FIELDS = {
    "nl_Literal_translation_en",
    "nl_Literal_translation_zh",
    "nl_Paraphrase_en",
    "nl_Paraphrase_zh",
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
        "issues": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "issues", "suggestions"],
    "additionalProperties": False,
}

INSTRUCTIONS = """You are an independent STL/NL semantic validator.
Review only the supplied candidate and do not assume facts outside it.
Check all four translations against the STL, including temporal and edge
operator direction, scope, interval, and nesting. Check signal grounding,
units, numeric plausibility, and natural engineering wording. rise/fall
semantics must be preserved naturally and must not be reduced to a state.
Return PASS only if there is no strengthening, weakening, omission, scope
error, edge error, unsupported numeric choice, or unnatural forced wording."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one candidate with an independent API request."
    )
    parser.add_argument("--input", required=True, help="Candidate request JSON")
    parser.add_argument("--output", help="Atomically write the result JSON here")
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL"),
        help="Model ID; defaults to OPENAI_MODEL",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        help="Responses API base URL",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate input and print the API payload without sending it",
    )
    return parser.parse_args()


def load_candidate(path: Path) -> dict[str, Any]:
    candidate = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(candidate, dict):
        raise ValueError("input must be a JSON object")

    missing = sorted(REQUIRED_FIELDS - candidate.keys())
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    translations = candidate["translations"]
    if not isinstance(translations, dict):
        raise ValueError("translations must be a JSON object")
    missing_translations = sorted(TRANSLATION_FIELDS - translations.keys())
    if missing_translations:
        raise ValueError(
            "missing translation fields: " + ", ".join(missing_translations)
        )
    return candidate


def build_payload(model: str, candidate: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "Strictly review this one candidate. This JSON is the complete review "
        "context:\n\n"
        + json.dumps(candidate, ensure_ascii=False, indent=2)
    )
    return {
        "model": model,
        "instructions": INSTRUCTIONS,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "stl_semantic_validation",
                "strict": True,
                "schema": VERDICT_SCHEMA,
            }
        },
    }


def extract_output_text(response: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(
                content.get("text"), str
            ):
                texts.append(content["text"])
    if not texts:
        raise ValueError("API response contained no output_text")
    return "".join(texts)


def call_api(
    payload: dict[str, Any],
    base_url: str,
    api_key: str,
    timeout: float,
    max_retries: int,
) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/responses"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    for attempt in range(max_retries + 1):
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == max_retries:
                raise RuntimeError(f"API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if attempt == max_retries:
                raise RuntimeError(f"API connection failed: {exc}") from exc

        time.sleep(min(2**attempt, 30))

    raise RuntimeError("unreachable retry state")


def validate_verdict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("validator output must be a JSON object")
    if value.get("verdict") not in {"PASS", "FAIL"}:
        raise ValueError("verdict must be PASS or FAIL")
    if not isinstance(value.get("issues"), list):
        raise ValueError("issues must be an array")
    if not isinstance(value.get("suggestions"), list):
        raise ValueError("suggestions must be an array")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    try:
        candidate = load_candidate(Path(args.input))
        if not args.model:
            raise ValueError("set --model or OPENAI_MODEL")
        payload = build_payload(args.model, candidate)

        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")

        response = call_api(
            payload, args.base_url, api_key, args.timeout, args.max_retries
        )
        verdict = validate_verdict(json.loads(extract_output_text(response)))
        result = {
            **verdict,
            "validator": {
                "provider": "responses_api",
                "model": args.model,
                "response_id": response.get("id"),
            },
        }

        if args.output:
            write_json_atomic(Path(args.output), result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["verdict"] == "PASS" else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
