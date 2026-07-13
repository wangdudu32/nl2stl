from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

from AST2STL import ast2stl  # noqa: E402


MODEL = "deepseek-v4-pro"
MAX_ATTEMPTS = 5

INPUT_CSV = ROOT / "dataset/deepstl_test_300_sample.csv"
SCHEMA_FILE = ROOT / "knowledge_base/ast_schema.txt"
OUTPUT_FILE = ROOT / "result/deepstl_with_ast_deepseek_v4_pro_result.txt"
FAIL_TIMES_FILE = ROOT / "tmp/fail_times.txt"
AST_INTERMEDIATE_FILE = ROOT / "result/ast_intermediate/deepstl_with_ast.jsonl"


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


def build_system_prompt(schema_text: str) -> str:
    return f"""You convert natural language STL requirements into AST JSON.

Output requirements:
- Return exactly one JSON object.
- The JSON object must be the AST root node itself.
- Do not wrap the AST in keys such as "ast", "result", or "schema".
- Do not output markdown, code fences, comments, or explanations.
- The JSON object must validate against the following JSON Schema.
- Use only operators and fields allowed by this JSON Schema.

JSON Schema:
{schema_text}
"""


def build_user_prompt(nl: str, error: str | None = None, previous_output: str | None = None) -> str:
    prompt = f"""Generate the AST JSON object for this natural language requirement.

Natural language requirement:
{nl}
"""
    if error is None:
        return prompt
    return f"""{prompt}

Your previous output failed validation.

Validation error:
{error}

Previous output:
{previous_output}

Regenerate one complete valid AST JSON object only.
"""


def make_client() -> Any:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ModuleNotFoundError:
        pass

    from openai import OpenAI

    return OpenAI()


def call_llm(client: Any, system_prompt: str, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def parse_ast(text: str) -> dict[str, Any]:
    ast = json.loads(text)
    if not isinstance(ast, dict):
        raise ValueError("LLM output must be a JSON object")
    return ast


def validate_ast(ast: dict[str, Any], validator: Draft202012Validator) -> None:
    errors = sorted(validator.iter_errors(ast), key=lambda item: tuple(map(str, item.absolute_path)))
    if not errors:
        return
    error = errors[0]
    location = "/".join(str(part) for part in error.absolute_path) or "<root>"
    raise ValueError(f"{location}: {error.message}")


def ast_to_stl(ast: dict[str, Any]) -> str:
    return ast2stl(json.dumps(ast, ensure_ascii=False, separators=(",", ":")))


def translate_one(
    client: Any,
    system_prompt: str,
    validator: Draft202012Validator,
    nl: str,
) -> tuple[dict[str, Any] | None, int, str | None]:
    error = None
    previous_output = None
    fail_times = 0

    for _ in range(MAX_ATTEMPTS):
        output = call_llm(client, system_prompt, build_user_prompt(nl, error, previous_output))
        try:
            ast = parse_ast(output)
            validate_ast(ast, validator)
            return ast, fail_times, None
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            fail_times += 1
            error = f"{type(exc).__name__}: {exc}"
            previous_output = output

    return None, fail_times, error


def append_ast_record(
    ast_file,
    taskid: int,
    english: str,
    gold_stl: str,
    ast: dict[str, Any] | None,
    fail_times: int,
    error: str | None,
) -> None:
    record = {
        "taskid": taskid,
        "english": english,
        "gold_stl": gold_stl,
        "status": "ok" if ast is not None else "fail",
        "ast": ast,
        "fail_times": fail_times,
        "error": error,
    }
    ast_file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    ast_file.flush()


def append_result(out_file, taskid: int, gold_stl: str, pred_stl: str, is_first: bool) -> None:
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


def main() -> None:
    client = make_client()
    schema_text, validator = load_schema()
    system_prompt = build_system_prompt(schema_text)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAIL_TIMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    AST_INTERMEDIATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with (
        INPUT_CSV.open(newline="", encoding="utf-8") as csv_file,
        OUTPUT_FILE.open("w", encoding="utf-8") as out_file,
        FAIL_TIMES_FILE.open("w", encoding="utf-8") as fail_file,
        AST_INTERMEDIATE_FILE.open("w", encoding="utf-8") as ast_file,
    ):
        reader = csv.DictReader(csv_file)
        out_file.write("{\n")

        for taskid, row in enumerate(reader):
            ast, fail_times, error = translate_one(client, system_prompt, validator, row["English"])
            append_ast_record(
                ast_file, taskid, row["English"], row["STL"], ast, fail_times, error
            )
            if ast is None:
                pred_stl = "fail"
            else:
                try:
                    pred_stl = ast_to_stl(ast)
                except (ValueError, KeyError, TypeError, IndexError) as exc:
                    pred_stl = "fail"
                    print(f"第{taskid}条数据的AST转STL失败: {type(exc).__name__}: {exc}")
            append_result(out_file, taskid, row["STL"], pred_stl, taskid == 0)
            append_fail_times(fail_file, taskid, fail_times)
            print(f"第{taskid}条数据已完成")

        out_file.write("\n}\n")


if __name__ == "__main__":
    main()
