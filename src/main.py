#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def _use_project_virtualenv() -> None:
    """Re-run with the repository virtualenv when another venv is active."""
    root = Path(__file__).resolve().parent.parent
    project_venv = root / ".venv"
    project_python = root / ".venv" / "bin" / "python"
    current_prefix = Path(sys.prefix).resolve()
    # 用户可能误激活 knowledge_base/.venv；入口自动切回项目根环境。
    if project_python.exists() and current_prefix != project_venv.resolve():
        os.execv(str(project_python), [str(project_python), str(Path(__file__).resolve()), *sys.argv[1:]])


_use_project_virtualenv()

from nl2stl_app.cli import main


if __name__ == "__main__":
    main()
