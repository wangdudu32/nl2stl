from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

from AST2STL import ast2stl  # noqa: E402


# 修改这两个全局变量即可切换输入的 AST 中间结果和输出的 STL 结果。
INPUT_AST_FILE = (
    ROOT
    / "result/ast_intermediate/deepstl_with_ast_template_operator_knowledge.jsonl"
)
OUTPUT_FILE = (
    ROOT
    / "result/deepstl_with_ast_template_operator_knowledge_remapped_result.txt"
)


def load_ast_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    taskids: set[int] = set()

    with path.open("r", encoding="utf-8") as ast_file:
        for line_number, line in enumerate(ast_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"第{line_number}行不是合法JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"第{line_number}行必须是JSON对象")
            if "taskid" not in record:
                raise ValueError(f"第{line_number}行缺少taskid")
            if "gold_stl" not in record:
                raise ValueError(f"第{line_number}行缺少gold_stl")

            taskid = record["taskid"]
            if not isinstance(taskid, int) or isinstance(taskid, bool):
                raise ValueError(f"第{line_number}行的taskid必须是整数")
            if taskid in taskids:
                raise ValueError(f"发现重复的taskid: {taskid}")

            taskids.add(taskid)
            records.append(record)

    return records


def convert_ast(record: dict[str, Any]) -> tuple[str, str | None]:
    taskid = record["taskid"]
    if record.get("status") != "ok":
        return "fail", f"taskid {taskid} 的AST生成状态不是ok"

    ast = record.get("ast")
    if not isinstance(ast, dict):
        return "fail", f"taskid {taskid} 缺少合法的AST对象"

    try:
        ast_json = json.dumps(ast, ensure_ascii=False, separators=(",", ":"))
        return ast2stl(ast_json), None
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return "fail", f"taskid {taskid} 的AST转STL失败: {type(exc).__name__}: {exc}"


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


def main() -> None:
    records = load_ast_records(INPUT_AST_FILE)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    failed_taskids: list[int] = []
    with OUTPUT_FILE.open("w", encoding="utf-8") as out_file:
        out_file.write("{\n")
        for index, record in enumerate(records):
            pred_stl, error = convert_ast(record)
            append_result(
                out_file,
                record["taskid"],
                str(record["gold_stl"]),
                pred_stl,
                index == 0,
            )
            if error is not None:
                failed_taskids.append(record["taskid"])
                print(error)
        out_file.write("\n}\n")

    print(f"AST记录数: {len(records)}")
    print(f"映射成功数: {len(records) - len(failed_taskids)}")
    print(f"映射失败数: {len(failed_taskids)}")
    if failed_taskids:
        print("失败taskid: " + ", ".join(map(str, failed_taskids)))
    print(f"STL结果已写入: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
