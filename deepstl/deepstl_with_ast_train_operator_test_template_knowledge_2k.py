from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

from AST2STL import ast2stl  # noqa: E402


MODEL = "deepseek-v4-pro"
MAX_ATTEMPTS = 5
API_MAX_RETRIES = 5
API_RETRY_INITIAL_SECONDS = 2.0
API_RETRY_MAX_SECONDS = 30.0
CHECKPOINT_VERSION = 1

INPUT_CSV = ROOT / "dataset/deepstl_test_2k.csv"
SCHEMA_FILE = ROOT / "knowledge_base/ast_schema.txt"
OPERATOR_KNOWLEDGE_FILE = ROOT / "knowledge_base/train_operator_knowledge.txt"
TEMPLATE_OPERATOR_KNOWLEDGE_FILE = ROOT / "knowledge_base/template_knowledge.txt"
OUTPUT_FILE = ROOT / "result/deepstl_with_ast_train_operator_test_template_knowledge_2k_deepseek_v4_pro_result.txt"
FAIL_TIMES_FILE = ROOT / "tmp/deepstl_with_ast_train_operator_test_template_knowledge_2k_fail_times.txt"
AST_INTERMEDIATE_FILE = ROOT / "result/ast_intermediate/deepstl_with_ast_train_operator_test_template_knowledge_2k.jsonl"
RUN_METADATA_FILE = AST_INTERMEDIATE_FILE.with_suffix(".meta.json")


class ResumeError(RuntimeError):
    pass


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


def build_system_prompt(
    schema_text: str,
    operator_knowledge: str,
    template_operator_knowledge: str,
) -> str:
    return f"""You convert natural language STL requirements into AST JSON.

Output requirements:
- Return exactly one JSON object.
- The JSON object must be the AST root node itself.
- Do not wrap the AST in keys such as "ast", "result", or "schema".
- Do not output markdown, code fences, comments, explanations, or STL text.
- The JSON object must validate against the following JSON Schema.
- Use only operators and fields allowed by this JSON Schema.
- Use the train operator knowledge and template operator knowledge only as semantic guidance for choosing the correct schema structure and operator.
- If the train/template operator knowledge conflicts with the JSON Schema, the JSON Schema takes precedence.
- Use operator names exactly as specified by the JSON Schema enum values, not symbolic aliases.

JSON Schema:
{schema_text}

Train operator knowledge:
{operator_knowledge}

Template operator knowledge:
{template_operator_knowledge}
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate DeepSTL 2k requirements with resume support."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--restart",
        action="store_true",
        help="discard the existing checkpoint and start again from task 0",
    )
    mode.add_argument(
        "--force-resume",
        action="store_true",
        help="resume even when checkpoint metadata is missing or no longer matches",
    )
    return parser.parse_args(argv)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_run_metadata(system_prompt: str) -> dict[str, Any]:
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "model": MODEL,
        "max_attempts": MAX_ATTEMPTS,
        "api_max_retries": API_MAX_RETRIES,
        "input_csv_sha256": sha256_bytes(INPUT_CSV.read_bytes()),
        "system_prompt_sha256": sha256_bytes(system_prompt.encode("utf-8")),
    }


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, sort_keys=True, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp_path, path)


def load_run_metadata(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResumeError(f"无法读取运行元数据 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResumeError(f"运行元数据不是JSON对象: {path}")
    return value


def metadata_differences(
    saved: dict[str, Any], current: dict[str, Any]
) -> list[tuple[str, Any, Any]]:
    return [
        (key, saved.get(key), current_value)
        for key, current_value in current.items()
        if saved.get(key) != current_value
    ]


def truncate_checkpoint(path: Path, size: int = 0) -> None:
    with path.open("r+b" if path.exists() else "w+b") as file:
        file.truncate(size)
        file.flush()
        os.fsync(file.fileno())


def read_checkpoint(path: Path) -> tuple[list[dict[str, Any]], bool]:
    if not path.exists() or path.stat().st_size == 0:
        return [], False

    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    records: list[dict[str, Any]] = []
    valid_end = 0
    recovered_tail = False

    for line_number, raw_line in enumerate(lines, start=1):
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if line_number != len(lines):
                raise ResumeError(f"checkpoint第{line_number}行损坏，不能安全续传: {exc}") from exc
            truncate_checkpoint(path, valid_end)
            recovered_tail = True
            break
        if not isinstance(record, dict):
            raise ResumeError(f"checkpoint第{line_number}行不是JSON对象")
        records.append(record)
        valid_end += len(raw_line)

    if not recovered_tail and records and not data.endswith(b"\n"):
        with path.open("ab") as file:
            file.write(b"\n")
            file.flush()
            os.fsync(file.fileno())

    return records, recovered_tail


def validate_checkpoint_records(
    records: list[dict[str, Any]], rows: list[dict[str, str]]
) -> None:
    if len(records) > len(rows):
        raise ResumeError(
            f"checkpoint包含{len(records)}条记录，但当前CSV只有{len(rows)}条数据"
        )

    required_fields = {"taskid", "english", "gold_stl", "ast", "fail_times"}
    for expected_taskid, record in enumerate(records):
        missing = sorted(required_fields - record.keys())
        if missing:
            raise ResumeError(
                f"checkpoint第{expected_taskid + 1}行缺少字段: {', '.join(missing)}"
            )
        if record["taskid"] != expected_taskid:
            raise ResumeError(
                f"checkpoint任务编号不连续: 预期{expected_taskid}，实际{record['taskid']}"
            )
        row = rows[expected_taskid]
        if record["english"] != row["English"] or record["gold_stl"] != row["STL"]:
            raise ResumeError(
                f"checkpoint中的task {expected_taskid}与当前CSV内容不一致"
            )
        if not isinstance(record["fail_times"], int) or record["fail_times"] < 0:
            raise ResumeError(f"checkpoint中的task {expected_taskid}具有非法fail_times")


def prepare_checkpoint(
    rows: list[dict[str, str]],
    current_metadata: dict[str, Any],
    restart: bool,
    force_resume: bool,
) -> list[dict[str, Any]]:
    if restart:
        truncate_checkpoint(AST_INTERMEDIATE_FILE)
        write_json_atomic(RUN_METADATA_FILE, current_metadata)
        print("已清空旧断点，将从第0条数据重新开始")
        return []

    records, recovered_tail = read_checkpoint(AST_INTERMEDIATE_FILE)
    validate_checkpoint_records(records, rows)
    if recovered_tail:
        print("检测到checkpoint末尾存在残缺记录，已回退到上一条完整记录")

    saved_metadata: dict[str, Any] | None
    try:
        saved_metadata = load_run_metadata(RUN_METADATA_FILE)
    except ResumeError:
        if records and not force_resume:
            raise
        saved_metadata = None
        if records:
            print("警告: 运行元数据损坏，正在按 --force-resume 继续")
        else:
            print("检测到无效的空checkpoint元数据，已创建新的运行元数据")

    if records and saved_metadata is None and not force_resume:
        raise ResumeError(
            "检测到旧checkpoint但缺少运行元数据。请使用 --restart 重新开始，"
            "或使用 --force-resume 明确接受混合配置的风险。"
        )

    differences = (
        metadata_differences(saved_metadata, current_metadata) if saved_metadata is not None else []
    )
    if records and differences and not force_resume:
        details = ", ".join(key for key, _, _ in differences)
        raise ResumeError(
            f"checkpoint运行配置已变化({details})。请使用 --restart，"
            "或使用 --force-resume 明确接受混合配置的风险。"
        )
    if records and differences and force_resume:
        details = ", ".join(key for key, _, _ in differences)
        print(f"警告: 正在强制续传，以下配置已经变化: {details}")
    elif records and saved_metadata is None and force_resume:
        print("警告: 正在续传没有配置指纹的旧checkpoint")

    if not records or force_resume:
        write_json_atomic(RUN_METADATA_FILE, current_metadata)

    return records


def make_client() -> Any:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ModuleNotFoundError:
        pass

    from openai import OpenAI

    return OpenAI()


def call_llm(client: Any, system_prompt: str, user_prompt: str) -> str:
    delay = API_RETRY_INITIAL_SECONDS
    last_error: Exception | None = None

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
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
        except Exception as exc:
            last_error = exc
            if attempt == API_MAX_RETRIES:
                break
            print(
                f"API调用失败，{delay:g}秒后重试"
                f"({attempt}/{API_MAX_RETRIES}): {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay = min(delay * 2, API_RETRY_MAX_SECONDS)

    assert last_error is not None
    raise RuntimeError(
        f"API调用连续失败{API_MAX_RETRIES}次: {type(last_error).__name__}: {last_error}"
    ) from last_error


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
        try:
            output = call_llm(client, system_prompt, build_user_prompt(nl, error, previous_output))
        except RuntimeError as exc:
            fail_times += 1
            return None, fail_times, f"{type(exc).__name__}: {exc}"
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
    os.fsync(ast_file.fileno())


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


def prediction_from_ast(ast: dict[str, Any] | None, taskid: int) -> str:
    if ast is None:
        return "fail"
    try:
        return ast_to_stl(ast)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        print(f"第{taskid}条数据的AST转STL失败: {type(exc).__name__}: {exc}")
        return "fail"


def rebuild_derived_outputs(records, out_file, fail_file) -> None:
    out_file.write("{\n")
    for index, record in enumerate(records):
        taskid = record["taskid"]
        pred_stl = prediction_from_ast(record["ast"], taskid)
        append_result(out_file, taskid, record["gold_stl"], pred_stl, index == 0)
        append_fail_times(fail_file, taskid, record["fail_times"])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    schema_text, validator = load_schema()
    operator_knowledge = load_operator_knowledge()
    template_operator_knowledge = load_template_operator_knowledge()
    system_prompt = build_system_prompt(
        schema_text,
        operator_knowledge,
        template_operator_knowledge,
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAIL_TIMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    AST_INTERMEDIATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with INPUT_CSV.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))

    current_metadata = build_run_metadata(system_prompt)
    try:
        completed_records = prepare_checkpoint(
            rows,
            current_metadata,
            restart=args.restart,
            force_resume=args.force_resume,
        )
    except ResumeError as exc:
        print(f"无法续传: {exc}", file=sys.stderr)
        return 2

    start_taskid = len(completed_records)
    with (
        OUTPUT_FILE.open("w", encoding="utf-8") as out_file,
        FAIL_TIMES_FILE.open("w", encoding="utf-8") as fail_file,
        AST_INTERMEDIATE_FILE.open("a", encoding="utf-8") as ast_file,
    ):
        rebuild_derived_outputs(completed_records, out_file, fail_file)
        if start_taskid:
            print(f"已恢复{start_taskid}条记录，将从第{start_taskid}条数据继续")

        interrupted = False
        last_completed = start_taskid - 1
        try:
            if start_taskid < len(rows):
                client = make_client()
                for taskid in range(start_taskid, len(rows)):
                    row = rows[taskid]
                    ast, fail_times, error = translate_one(
                        client, system_prompt, validator, row["English"]
                    )
                    append_ast_record(
                        ast_file,
                        taskid,
                        row["English"],
                        row["STL"],
                        ast,
                        fail_times,
                        error,
                    )
                    last_completed = taskid
                    pred_stl = prediction_from_ast(ast, taskid)
                    append_result(out_file, taskid, row["STL"], pred_stl, taskid == 0)
                    append_fail_times(fail_file, taskid, fail_times)
                    print(f"第{taskid}条数据已完成")
        except KeyboardInterrupt:
            interrupted = True
            next_taskid = last_completed + 1
            if last_completed >= 0:
                print(
                    f"\n运行已中断，完整断点已保存至第{last_completed}条数据；"
                    f"下次将从第{next_taskid}条数据继续。"
                )
            else:
                print("\n运行已中断，尚无完整断点；下次将从第0条数据继续。")
        finally:
            out_file.write("\n}\n")
            out_file.flush()

    if interrupted:
        return 130
    if start_taskid == len(rows):
        print(f"checkpoint已包含全部{len(rows)}条数据，结果文件已重建")
    else:
        print(f"全部{len(rows)}条数据已完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
