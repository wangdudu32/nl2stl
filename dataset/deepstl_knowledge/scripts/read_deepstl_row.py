#!/usr/bin/env python3
"""Read exactly one raw DeepSTL CSV row.

This utility performs no parsing, normalization, classification, extraction,
deduplication, aggregation, or knowledge-base writing.  All knowledge work is
performed by the LLM after it receives the raw row.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "train": (ROOT / "deepstl_train_14k.csv", "stl"),
    "test": (ROOT / "deepstl_test_2k.csv", "STL"),
}


def read_one(split: str, row_number: int) -> dict[str, str | int]:
    path, stl_column = SOURCES[split]
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        for current, row in enumerate(reader, 1):
            if current == row_number:
                return {
                    "row": row_number,
                    "split": split,
                    "stl": row[stl_column],
                    "English": row["English"],
                    "Type": row["Type"],
                }
    raise SystemExit(f"row {row_number} does not exist in {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=sorted(SOURCES), required=True)
    parser.add_argument("--row", type=int, required=True)
    args = parser.parse_args()
    if args.row < 1:
        raise SystemExit("--row must be at least 1")
    print(json.dumps(read_one(args.split, args.row), ensure_ascii=False))


if __name__ == "__main__":
    main()
