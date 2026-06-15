#!/usr/bin/env python3
"""Validate a JSON STL formula against the AST Schema.

Usage:
    python validate_stl.py <json_file_or_string>

Returns exit code 0 if valid, 1 if invalid.
"""

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("Error: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR.parent / "knowledge_base" / "ast_schema.txt"


def load_schema() -> dict:
    """Load JSON Schema from the references file."""
    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in schema file")
    return json.loads(raw[start:])


def validate(data: dict) -> list[str]:
    """Validate a single STL JSON object. Returns list of error messages."""
    schema = load_schema()
    validator = Draft202012Validator(schema)
    return [f"{err.message} (path: {list(err.path)})" for err in validator.iter_errors(data)]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python validate_stl.py <json_file_or_string>", file=sys.stderr)
        return 1

    arg = sys.argv[1]

    # Try as file path first (only if it looks like a path)
    path = Path(arg)
    if len(arg) < 256 and path.exists():
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    else:
        # Try as JSON string
        data = json.loads(arg)

    errors = validate(data)

    if errors:
        print("INVALID - Validation errors:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("VALID - JSON conforms to STL Schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
