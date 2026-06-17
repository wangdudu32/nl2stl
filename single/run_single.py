#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _use_project_virtualenv() -> None:
    project_venv = ROOT / ".venv"
    project_python = project_venv / "bin" / "python"
    if project_python.exists() and Path(sys.prefix).resolve() != project_venv.resolve():
        os.execv(str(project_python), [str(project_python), str(Path(__file__).resolve()), *sys.argv[1:]])


_use_project_virtualenv()

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nl2stl_app.cli import main


if __name__ == "__main__":
    main()
