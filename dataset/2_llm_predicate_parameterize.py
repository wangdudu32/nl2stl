#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path


INPUT_PATH = Path("1_deepstl_para.csv")
OUTPUT_PATH = Path("gpt/2_deepstl_pred_para.csv")
SCHEMA_PATH = Path("gpt/llm_predicate_output_schema.json")

FIELDNAMES = ["STL", "English", "Type", "Predicate_Map", "Status"]
ERROR_LOG_PATH = Path("gpt/2_deepstl_pred_para.errors.log")


class RetryableLLMError(RuntimeError):
    pass


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "STL": {"type": "string"},
        "English": {"type": "string"},
        "Predicate_Map": {"type": "string"},
    },
    "required": ["STL", "English", "Predicate_Map"],
}


def ensure_schema() -> None:
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SCHEMA_PATH.exists():
        SCHEMA_PATH.write_text(json.dumps(SCHEMA, indent=2), encoding="utf-8")


def count_completed_rows() -> int:
    if not OUTPUT_PATH.exists():
        return 0
    with OUTPUT_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for _ in reader)


def pred_names(text: str) -> set[str]:
    return set(re.findall(r"\bpred\d+\b", text))


def status_for(stl: str, english: str, predicate_map: str) -> str:
    stl_preds = pred_names(stl)
    english_preds = pred_names(english)
    map_preds = pred_names(predicate_map)
    parts = []
    if stl_preds != english_preds:
        parts.append(
            "pred_mismatch "
            f"stl_only={sorted(stl_preds - english_preds)} "
            f"nl_only={sorted(english_preds - stl_preds)}"
        )
    if stl_preds != map_preds:
        parts.append(
            "map_mismatch "
            f"stl_only={sorted(stl_preds - map_preds)} "
            f"map_only={sorted(map_preds - stl_preds)}"
        )
    if re.search(r"\bsig\d+\b", english):
        parts.append("nl_has_sig")
    return "ok" if not parts else " | ".join(parts)


def prompt_for(index: int, row: dict[str, str]) -> str:
    return f"""You transform one NL-STL template pair into predicate-level parameterized templates.

Rules:
- Treat this row independently. Predicate numbering starts from pred1 for this row.
- Identify atomic STL predicates such as "sig1 < val1", "sig2 == sig3", and bounded-range comparisons.
- Replace each atomic predicate in STL with pred1, pred2, ... in first-appearance order.
- Replace the corresponding natural-language predicate meaning in English with the same predN.
- Preserve temporal operators, Boolean structure, timing parameters, and response/trigger wording.
- The English and STL outputs must contain exactly the same set of predN tokens.
- Do not leave sigN or valN tokens in English unless they are part of timing text, which should normally not happen.
- Predicate_Map must explain the local mapping, e.g. "pred1 = sig1 < val1; pred2 = sig2 == sig3".
- It is acceptable and preferred for English to contain compact logical/event phrases such as "pred1 and pred2", "not (pred2 and pred3)", and "rise(pred1)" when that preserves alignment.
- Do not paraphrase a predicate into words after replacing it with predN.
- Return only valid JSON matching the requested schema.

Examples:
- STL "eventually [t1:t2] (rise (sig1 >= val1 and sig1 <= val2))"
  becomes "eventually [t1:t2] (rise (pred1 and pred2))"
  and English should say that "rise(pred1 and pred2)" is observed within t1 to t2 time units.
- STL "always ( rise (sig1 == val1) -> not (sig2 >= val2 and sig2 <= val3) )"
  becomes "always ( rise (pred1) -> not (pred2 and pred3) )"
  and English should keep "rise(pred1)" and "not (pred2 and pred3)" with the original trigger/response timing.

Row index: {index}
Type: {row["Type"]}
Original STL:
{row["STL"]}

Original English:
{row["English"]}
"""


def is_retryable_error(text: str) -> bool:
    lowered = text.lower()
    retryable_markers = [
        "rate limit",
        "ratelimit",
        "quota",
        "usage limit",
        "429",
        "too many requests",
        "temporarily unavailable",
        "timeout",
        "timed out",
        "connection reset",
        "network",
        "try again",
    ]
    return any(marker in lowered for marker in retryable_markers)


def call_codex(prompt: str, model: str) -> dict[str, str]:
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tmp:
        output_path = tmp.name
    try:
        command = [
            "codex",
            "exec",
            "--cd",
            str(Path.cwd()),
            "--skip-git-repo-check",
            "--model",
            model,
            "--output-schema",
            str(SCHEMA_PATH),
            "--output-last-message",
            output_path,
            prompt,
        ]
        proc = subprocess.run(command, text=True, capture_output=True)
        if proc.returncode != 0:
            detail = (proc.stderr or "") + "\n" + (proc.stdout or "")
            detail = detail.strip()
            if is_retryable_error(detail):
                raise RetryableLLMError(detail)
            raise RuntimeError(detail or f"codex exited with status {proc.returncode}")
        raw = Path(output_path).read_text(encoding="utf-8").strip()
        return json.loads(raw)
    finally:
        try:
            Path(output_path).unlink()
        except FileNotFoundError:
            pass


def write_output_row(writer: csv.DictWriter, handle, row: dict[str, str]) -> None:
    writer.writerow(row)
    handle.flush()
    os.fsync(handle.fileno())


def append_error_log(message: str) -> None:
    ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="maximum number of new rows to process")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--restart", action="store_true", help="overwrite the output and start at row 1")
    parser.add_argument("--retry-sleep", type=int, default=900, help="seconds to wait before retrying quota/rate/network errors")
    parser.add_argument("--error-sleep", type=int, default=60, help="seconds to wait before retrying non-quota errors")
    parser.add_argument("--max-failures-per-row", type=int, default=3, help="stop instead of polluting the CSV after this many non-quota failures")
    args = parser.parse_args()

    ensure_schema()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if args.restart and OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    completed = count_completed_rows()
    mode = "a" if OUTPUT_PATH.exists() else "w"

    with INPUT_PATH.open(newline="", encoding="utf-8") as source, OUTPUT_PATH.open(
        mode, newline="", encoding="utf-8"
    ) as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=FIELDNAMES)
        if mode == "w":
            writer.writeheader()
            target.flush()
            os.fsync(target.fileno())

        processed = 0
        for index, row in enumerate(reader, start=1):
            if index <= completed:
                continue
            if args.limit is not None and processed >= args.limit:
                break

            failures = 0
            while True:
                try:
                    result = call_codex(prompt_for(index, row), args.model)
                    stl = result["STL"].strip()
                    english = result["English"].strip()
                    predicate_map = result["Predicate_Map"].strip()
                    status = status_for(stl, english, predicate_map)
                    if status != "ok":
                        raise ValueError(f"validation failed: {status}")
                    break
                except RetryableLLMError as exc:
                    print(
                        f"row {index}: retryable_error; sleeping {args.retry_sleep}s before retry: {exc}",
                        flush=True,
                    )
                    time.sleep(args.retry_sleep)
                except Exception as exc:
                    failures += 1
                    message = f"row {index}: failure {failures}/{args.max_failures_per_row}: {type(exc).__name__}: {exc}"
                    append_error_log(message)
                    print(message, flush=True)
                    if failures >= args.max_failures_per_row:
                        raise SystemExit(
                            f"Stopping at row {index}; not writing an invalid row to {OUTPUT_PATH}. "
                            f"See {ERROR_LOG_PATH}."
                        )
                    time.sleep(args.error_sleep)

            write_output_row(
                writer,
                target,
                {
                    "STL": stl,
                    "English": english,
                    "Type": row["Type"],
                    "Predicate_Map": predicate_map,
                    "Status": status,
                },
            )
            processed += 1
            print(f"row {index}: {status}", flush=True)


if __name__ == "__main__":
    main()
