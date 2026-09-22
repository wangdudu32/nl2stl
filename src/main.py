"""逐条调用 LLM 将 DeepSTL 自然语言转换为 DSL，再确定性转换为 STL。"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from dsl_to_stl import convert_dsl_to_stl
from dsl_validator import validate_dsl


# ======================== 请在这里填写/修改模型名称 ========================
load_dotenv()

MODEL_NAME = "deepseek-v4-pro"

# DSL 最多生成 5 次。失败结果的 pred_stl 按需求写成字符串 "nlll"。
MAX_DSL_GENERATIONS = 5
FAILED_PRED_STL = "nlll"

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DATA_PATH = BASE_DIR.parent / "dataset" / "deepstl_test_300_sample.csv"
DSL_SPEC_PATH = BASE_DIR.parent / "knowledge_base" / "dsl_step1.md"
INTERMEDIATE_PATH = (
    BASE_DIR.parent
    / "result"
    / "mediate_result"
    / "DeepSTL_with_dsl_mediate_result.jsonl"
)
RESULT_PATH = BASE_DIR.parent / "result" / "DeepSTL_with_dsl_result.txt"


def load_rows() -> list[dict[str, str]]:
    """读取 CSV，并检查本实验需要的列。"""
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required_columns = {"English", "STL"}
        if not required_columns.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV 必须包含这些列：{sorted(required_columns)}")
        return list(reader)


def repair_incomplete_jsonl_tail() -> None:
    """修复意外中断留下的不完整末行，并确保完整末行以换行结束。"""
    if not INTERMEDIATE_PATH.exists():
        return

    data = INTERMEDIATE_PATH.read_bytes()
    if not data or data.endswith(b"\n"):
        return

    last_newline = data.rfind(b"\n")
    tail = data[last_newline + 1 :]
    try:
        json.loads(tail.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        with INTERMEDIATE_PATH.open("rb+") as file:
            file.truncate(last_newline + 1)
        print("检测到 JSONL 不完整末行，已移除并将在本次运行中重新处理。")
    else:
        with INTERMEDIATE_PATH.open("ab") as file:
            file.write(b"\n")
            file.flush()
            os.fsync(file.fileno())


def load_intermediate(rows: list[dict[str, str]]) -> dict[int, dict]:
    """读取 JSONL；success 和 fail 都表示该 task_id 已经处理完。"""
    repair_incomplete_jsonl_tail()
    records: dict[int, dict] = {}
    if not INTERMEDIATE_PATH.exists():
        return records

    required_fields = {"task_id", "nl", "dsl", "status", "times"}
    with INTERMEDIATE_PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"中间文件第 {line_number} 行不是合法 JSON") from error

            if set(record) != required_fields:
                raise ValueError(
                    f"中间文件第 {line_number} 行字段必须恰好为 {sorted(required_fields)}"
                )

            task_id = record["task_id"]
            status = record["status"]
            times = record["times"]
            if not isinstance(task_id, int) or not 0 <= task_id < len(rows):
                raise ValueError(f"中间文件第 {line_number} 行 task_id 无效")
            if task_id in records:
                raise ValueError(f"中间文件中 task_id={task_id} 重复")
            if record["nl"] != rows[task_id]["English"]:
                raise ValueError(f"task_id={task_id} 的 nl 与当前 CSV 不一致")
            if status not in {"success", "fail"}:
                raise ValueError(f"task_id={task_id} 的 status 无效：{status!r}")
            if not isinstance(times, int) or not 1 <= times <= MAX_DSL_GENERATIONS:
                raise ValueError(f"task_id={task_id} 的 times 无效：{times!r}")
            if status == "fail" and times != MAX_DSL_GENERATIONS:
                raise ValueError(f"task_id={task_id} 状态为 fail 时 times 必须为 5")
            if not isinstance(record["dsl"], str):
                raise ValueError(f"task_id={task_id} 的 dsl 必须是字符串")

            records[task_id] = record

    return records


def append_intermediate(record: dict) -> None:
    """将一条最终状态追加到 JSONL，并立即同步到磁盘。"""
    INTERMEDIATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with INTERMEDIATE_PATH.open("a", encoding="utf-8") as file:
        file.write(line)
        file.flush()
        os.fsync(file.fileno())


def write_result(rows: list[dict[str, str]], records: dict[int, dict]) -> None:
    """根据 CSV 和全部中间记录，原子重建最终结果文件。"""
    result_lines = ["{"]
    task_ids = sorted(records)

    for index, task_id in enumerate(task_ids):
        record = records[task_id]
        if record["status"] == "success":
            pred_stl = convert_dsl_to_stl(record["dsl"])
        else:
            pred_stl = FAILED_PRED_STL

        result_lines.extend(
            [
                "  {",
                f"    taskid:{task_id},",
                f"    gold_stl:{json.dumps(rows[task_id]['STL'], ensure_ascii=False)},",
                f"    pred_stl:{json.dumps(pred_stl, ensure_ascii=False)},",
                "  }," if index < len(task_ids) - 1 else "  }",
            ]
        )

    result_lines.append("}")
    content = "\n".join(result_lines) + "\n"

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = RESULT_PATH.with_suffix(RESULT_PATH.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary_path, RESULT_PATH)


def clean_dsl(text: str) -> str:
    """去除模型偶尔添加在 DSL 外层的 Markdown 代码围栏。"""
    text = text.strip()
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def request_dsl(
    client: OpenAI,
    specification: str,
    nl: str,
    previous_dsl: str | None,
    validation_error: str | None,
) -> str:
    """向 LLM 请求一份完整 DSL；验证失败时附上上一版及错误。"""
    system_prompt = (
        "你负责把英文自然语言需求转换成下面规范定义的 DSL。"
        "必须严格遵守规范，只输出完整 DSL 正文，不要解释，不要 Markdown 代码围栏，"
        "也不要输出 STL。\n\n"
        f"DSL 规范：\n{specification}"
    )

    if previous_dsl is None:
        user_prompt = f"请将下面的自然语言转换为 DSL：\n\n{nl}"
    else:
        user_prompt = (
            "下面的 DSL 没有通过语法验证。请根据错误重新生成一份完整 DSL，"
            "并且只输出修正后的 DSL 正文。\n\n"
            f"原始自然语言：\n{nl}\n\n"
            f"上一次 DSL：\n{previous_dsl}\n\n"
            f"验证错误：\n{validation_error}"
        )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return clean_dsl(response.choices[0].message.content or "")


def generate_and_validate_dsl(
    client: OpenAI, specification: str, task_id: int, nl: str
) -> tuple[str, str, int]:
    """最多生成 5 次 DSL，返回 (dsl, 最终状态, 生成次数)。"""
    dsl = ""
    error: str | None = None

    for times in range(1, MAX_DSL_GENERATIONS + 1):
        dsl = request_dsl(client, specification, nl, dsl if times > 1 else None, error)
        valid, error = validate_dsl(dsl)
        if valid:
            print(f"task_id={task_id}: DSL 第 {times} 次生成后验证成功")
            return dsl, "success", times
        print(f"task_id={task_id}: DSL 第 {times} 次验证失败：{error}")

    return dsl, "fail", MAX_DSL_GENERATIONS


def create_client() -> OpenAI:
    """读取 .env 并创建 OpenAI 兼容客户端。"""
    load_dotenv(ENV_PATH)
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not MODEL_NAME.strip():
        raise ValueError("请先在 main.py 顶部填写 MODEL_NAME")
    if not api_key:
        raise ValueError(f"{ENV_PATH} 中缺少 OPENAI_API_KEY")
    if not base_url:
        raise ValueError(f"{ENV_PATH} 中缺少 OPENAI_BASE_URL")

    # SDK 自动重试网络错误、超时和部分服务端错误；这些重试不计入 times。
    return OpenAI(api_key=api_key, base_url=base_url, max_retries=3, timeout=120.0)


def main() -> None:
    rows = load_rows()
    specification = DSL_SPEC_PATH.read_text(encoding="utf-8")
    records = load_intermediate(rows)

    # 启动时先恢复最终文件，处理“JSONL 已写入但结果文件尚未刷新”的中断情况。
    write_result(rows, records)
    print(f"共 {len(rows)} 条数据，断点中已有 {len(records)} 条。")

    if len(records) == len(rows):
        print(f"全部任务均已完成，结果文件：{RESULT_PATH}")
        return

    client = create_client()

    for task_id, row in enumerate(rows):
        if task_id in records:
            continue

        print(f"[{task_id + 1}/{len(rows)}] 正在处理 task_id={task_id}")
        dsl, status, times = generate_and_validate_dsl(
            client, specification, task_id, row["English"]
        )
        record = {
            "task_id": task_id,
            "nl": row["English"],
            "dsl": dsl,
            "status": status,
            "times": times,
        }

        # 先持久化中间记录，再刷新最终结果；若其间中断，下次启动会自动重建结果。
        append_intermediate(record)
        records[task_id] = record
        write_result(rows, records)
        print(f"task_id={task_id}: 已保存，status={status}, times={times}")

    success_count = sum(record["status"] == "success" for record in records.values())
    fail_count = sum(record["status"] == "fail" for record in records.values())
    print(f"处理完成：success={success_count}, fail={fail_count}")
    print(f"中间结果：{INTERMEDIATE_PATH}")
    print(f"最终结果：{RESULT_PATH}")


if __name__ == "__main__":
    main()
