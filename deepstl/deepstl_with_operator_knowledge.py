from __future__ import annotations

import csv
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


MODEL = "deepseek-v4-pro"

INPUT_CSV = Path("../dataset/deepstl_test_300_sample.csv")
OPERATOR_KNOWLEDGE_FILE = Path("../knowledge_base/stl_operator_knowledge.txt")
OUTPUT_FILE = Path("../result/deepstl_with_operator_knowledge_deepseek_v4_pro_result.txt")

ALLOWED_OPERATORS = """\
Temporal operators: always, eventually, until, weak_until, release, once, historically, since
Edge operators: rise, fall
Boolean operators: not, and, or, ->, <->
Comparison operators: >, >=, ==, <, <=
"""


def load_operator_knowledge() -> str:
    return OPERATOR_KNOWLEDGE_FILE.read_text(encoding="utf-8").strip()


def build_prompt(description: str, operator_knowledge: str) -> str:
    return f"""Convert the following natural language requirement into one STL formula.

Allowed operators:
{ALLOWED_OPERATORS}

STL operator knowledge:
{operator_knowledge}

Use the STL operator knowledge as semantic guidance for choosing the correct operator.
Use only the allowed operator words/symbols listed above.
Do not output knowledge category names such as always_eventually, eventually_fall, or always_not_rise as STL operators.

Prefer literal, form-preserving translation.
Do not rewrite an expression into a logically equivalent but structurally different form.
Preserve the operator and comparison direction implied by the natural language whenever possible.

Do not use shorthand or symbolic aliases such as G, F, U, R, O, H, S, !, &&, ||, ¬, ∧, ∨, →, ↔.
Do not output AST, JSON, explanations, markdown, or code fences.
Output only the STL formula.

Natural language requirement:
{description}
"""


def call_llm(client: OpenAI, prompt: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You translate natural language requirements into STL formulas."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main() -> None:
    load_dotenv()
    client = OpenAI()
    operator_knowledge = load_operator_knowledge()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with INPUT_CSV.open(newline="", encoding="utf-8") as csv_file, OUTPUT_FILE.open("w", encoding="utf-8") as out_file:
        reader = csv.DictReader(csv_file)
        out_file.write("{\n")

        for taskid, row in enumerate(reader):
            english = row["English"]
            gold_stl = row["STL"]

            prompt = build_prompt(english, operator_knowledge)
            pred_stl = call_llm(client, prompt)

            if taskid > 0:
                out_file.write(",\n")
            out_file.write(
                f"  {{\n"
                f"    taskid:{taskid},\n"
                f'    gold_stl:"{quote(gold_stl)}",\n'
                f'    pred_stl:"{quote(pred_stl)}",\n'
                f"  }}"
            )
            out_file.flush()
            print(f"taskid {taskid} completed")

        out_file.write("\n}\n")


if __name__ == "__main__":
    main()
