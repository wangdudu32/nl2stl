#!/usr/bin/env python3
import argparse
import csv
import fcntl
import importlib.util
import json
import os
import sys
import time
from pathlib import Path


BASE_SCRIPT = Path("2_llm_predicate_parameterize.py")
INPUT_PATH = Path("1_deepstl_para.csv")
OUTPUT_PATH = Path("gpt/2_deepstl_pred_para.csv")
LOCK_PATH = Path("gpt/2_deepstl_pred_para.lock")
STATE_PATH = Path("gpt/2_deepstl_pred_para.state.json")
LOG_PATH = Path("gpt/2_deepstl_pred_para.log")

FIELDNAMES = ["Row_Index", "STL", "English", "Type", "Predicate_Map", "Status"]


def load_base():
    spec = importlib.util.spec_from_file_location("llm_pred_base", BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ensure_schema()
    return module


def read_input_rows() -> list[dict[str, str]]:
    with INPUT_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_output_rows() -> list[dict[str, str]]:
    if not OUTPUT_PATH.exists():
        return []
    with OUTPUT_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_all_rows(rows: list[dict[str, str]]) -> None:
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def normalize_existing_output() -> None:
    rows = read_output_rows()
    if not rows:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_all_rows([])
        return
    if "Row_Index" in rows[0]:
        return
    normalized = []
    for index, row in enumerate(rows, start=1):
        normalized.append(
            {
                "Row_Index": str(index),
                "STL": row["STL"],
                "English": row["English"],
                "Type": row["Type"],
                "Predicate_Map": row["Predicate_Map"],
                "Status": row["Status"],
            }
        )
    write_all_rows(normalized)


def append_log(message: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"in_progress": {}, "retries": {}}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def completed_indexes() -> set[int]:
    done = set()
    for row in read_output_rows():
        value = row.get("Row_Index")
        if value:
            done.add(int(value))
    return done


def claim_row(total: int, worker_id: str, stale_seconds: int) -> int | None:
    now = time.time()
    with LOCK_PATH.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        normalize_existing_output()
        done = completed_indexes()
        state = load_state()
        in_progress = state.setdefault("in_progress", {})
        for key, claim in list(in_progress.items()):
            if now - float(claim.get("time", 0)) > stale_seconds:
                del in_progress[key]
        for index in range(1, total + 1):
            key = str(index)
            if index not in done and key not in in_progress:
                in_progress[key] = {"worker": worker_id, "time": now}
                save_state(state)
                fcntl.flock(lock, fcntl.LOCK_UN)
                return index
        fcntl.flock(lock, fcntl.LOCK_UN)
        return None


def finish_row(index: int, output_row: dict[str, str], worker_id: str) -> None:
    with LOCK_PATH.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = read_output_rows()
        if not any(int(row["Row_Index"]) == index for row in rows):
            with OUTPUT_PATH.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
                writer.writerow(output_row)
                handle.flush()
                os.fsync(handle.fileno())
        state = load_state()
        state.setdefault("in_progress", {}).pop(str(index), None)
        save_state(state)
        append_log(f"worker {worker_id} row {index}: {output_row['Status']}")
        fcntl.flock(lock, fcntl.LOCK_UN)


def worker(args) -> None:
    base = load_base()
    rows = read_input_rows()
    total = len(rows)
    while True:
        index = claim_row(total, args.worker_id, args.stale_seconds)
        if index is None:
            return
        source_row = rows[index - 1]
        try:
            result = base.call_codex(base.prompt_for(index, source_row), args.model)
            stl = result["STL"].strip()
            english = result["English"].strip()
            predicate_map = result["Predicate_Map"].strip()
            status = base.status_for(stl, english, predicate_map)
        except Exception as exc:
            stl = ""
            english = ""
            predicate_map = ""
            status = f"llm_error row={index} error={type(exc).__name__}: {exc}"
        finish_row(
            index,
            {
                "Row_Index": str(index),
                "STL": stl,
                "English": english,
                "Type": source_row["Type"],
                "Predicate_Map": predicate_map,
                "Status": status,
            },
            args.worker_id,
        )


def status() -> None:
    normalize_existing_output()
    rows = read_output_rows()
    done = {int(row["Row_Index"]) for row in rows}
    bad = [row for row in rows if row["Status"] != "ok"]
    print(f"completed={len(done)}/2000")
    print(f"bad={len(bad)}")
    if bad[:10]:
        print("first_bad=" + ", ".join(f"{r['Row_Index']}:{r['Status']}" for r in bad[:10]))


def finalize() -> None:
    normalize_existing_output()
    rows = read_output_rows()
    rows.sort(key=lambda row: int(row["Row_Index"]))
    write_all_rows(rows)
    status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", default=f"worker-{os.getpid()}")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--stale-seconds", type=int, default=1800)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.status:
        status()
        return
    if args.finalize:
        finalize()
        return
    worker(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
