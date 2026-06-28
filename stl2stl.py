import csv
import json
from pathlib import Path

from AST2STL import ast2stl
from STL2AST import stl2ast


INPUT_FILE = Path("dataset/deepstl_test_2k.csv")
OUTPUT_FILE = Path("tmp/stl2stl.txt")


def quote(text):
    return json.dumps(text, ensure_ascii=False)


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with INPUT_FILE.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))

    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        out.write("{\n")
        for taskid, row in enumerate(rows):
            gold_stl = row["STL"]
            pred_stl = ast2stl(stl2ast(gold_stl))
            comma = "," if taskid < len(rows) - 1 else ""
            out.write(
                "  {\n"
                f"    taskid:{taskid},\n"
                f"    gold_stl:{quote(gold_stl)},\n"
                f"    pred_stl:{quote(pred_stl)},\n"
                f"  }}{comma}\n"
            )
        out.write("}\n")


if __name__ == "__main__":
    main()
