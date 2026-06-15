#!/usr/bin/env python3
"""Convert a JSON STL formula to a human-readable string.

Usage:
    python ast2stl.py <json_file_or_string>
"""

import json
import sys
from pathlib import Path

from nl2stl_app.converter import STLJSONToStringConverter


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python ast2stl.py <json_file_or_string>", file=sys.stderr)
        return 1

    arg = sys.argv[1]
    path = Path(arg)
    if len(arg) < 256 and path.exists():
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    else:
        data = json.loads(arg)

    converter = STLJSONToStringConverter()
    result = converter.convert(data)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
