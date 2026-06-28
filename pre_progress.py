import argparse
import csv
import os
from pathlib import Path

from AST2STL import ast2stl
from STL2AST import stl2ast


DEFAULT_FILE = Path("dataset/deepstl_300_sample_copy.csv")


class STLPreProgressError(RuntimeError):
    """Raised when an STL formula cannot pass the stl -> ast -> stl conversion."""


def pre_progress(file_path):
    """Replace each STL formula in a CSV with ast2stl(stl2ast(formula))."""
    path = Path(file_path)

    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"{path} is empty or missing a CSV header")
        if "STL" not in reader.fieldnames:
            raise ValueError(f"{path} must contain an STL column")

        rows = []
        for index, row in enumerate(reader, start=1):
            original_stl = row["STL"]
            try:
                row["STL"] = ast2stl(stl2ast(original_stl))
            except Exception as exc:
                csv_line = index + 1
                raise STLPreProgressError(
                    f"failed to convert STL at CSV line {csv_line}: {original_stl}"
                ) from exc
            rows.append(row)

    tmp_path = path.with_name(f".{path.name}.tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    os.replace(tmp_path, path)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Normalize CSV STL formulas through stl -> ast schema -> stl."
    )
    parser.add_argument(
        "file_path",
        nargs="?",
        default=DEFAULT_FILE,
        help=f"CSV file to update in place. Defaults to {DEFAULT_FILE}",
    )
    args = parser.parse_args()

    count = pre_progress(args.file_path)
    print(f"processed {count} rows: {args.file_path}")


if __name__ == "__main__":
    main()
