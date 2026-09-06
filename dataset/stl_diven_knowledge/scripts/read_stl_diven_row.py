#!/usr/bin/env python3
"""Read exactly one raw STL-Diven CSV row.

This utility performs no STL parsing, normalization, classification,
extraction, deduplication, aggregation, or knowledge-base writing. All
knowledge work is performed by the LLM after it receives the raw row.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "stl_diven_6970.csv"


def read_one(row_number: int) -> dict[str, str | int]:
    with SOURCE.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        for current, row in enumerate(reader, 1):
            if current == row_number:
                return {
                    "row": row_number,
                    "stl": row["STL"],
                    "English": row["English"],
                    "Complexity": row["Complexity"],
                }
    raise SystemExit(f"row {row_number} does not exist in {SOURCE.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", type=int, required=True)
    args = parser.parse_args()
    if args.row < 1:
        raise SystemExit("--row must be at least 1")
    print(json.dumps(read_one(args.row), ensure_ascii=False))


if __name__ == "__main__":
    main()
