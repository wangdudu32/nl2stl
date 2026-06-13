from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    signals_path: Path
    operators_path: Path
    openai_model: str
    openai_api_key: str
    openai_base_url: str | None
    tavily_api_key: str | None
    request_timeout_seconds: float

    @classmethod
    def load(cls, root_dir: Path | None = None) -> "Settings":
        root = (root_dir or Path.cwd()).resolve()
        load_dotenv(root / ".env")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required in .env")
        return cls(
            root_dir=root,
            signals_path=root / "signals_kb.txt",
            operators_path=root / "stl_operators.md",
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            openai_api_key=api_key,
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        )
