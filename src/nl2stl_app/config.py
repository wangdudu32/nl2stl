from __future__ import annotations

import json
import os
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = ROOT / "knowledge_base"


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    """外部服务和重试策略配置。"""

    api_key: str
    base_url: str
    tavily_api_key: str | None
    model: str
    timeout_seconds: float
    max_llm_attempts: int
    max_ast_repairs: int

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(ROOT / "src" / ".env")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        if not api_key or not base_url:
            raise ConfigurationError("src/.env 缺少 OPENAI_API_KEY 或 OPENAI_BASE_URL")
        return cls(
            api_key=api_key,
            base_url=base_url,
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip() or None,
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
            timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
            max_llm_attempts=int(os.getenv("MAX_LLM_ATTEMPTS", "3")),
            max_ast_repairs=int(os.getenv("MAX_AST_REPAIRS", "3")),
        )


class RuntimeCatalog:
    """Loads prompts and intermediate JSON Schemas from their single sources."""

    def __init__(self) -> None:
        self.prompt_document = self._load_json(KNOWLEDGE_DIR / "prompt.json")
        self.format_document = self._load_json(KNOWLEDGE_DIR / "data_formats.json")
        self.prompts = self.prompt_document["prompts"]
        self.formats = self.format_document["formats"]
        self._validate_catalog()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"无法加载配置 {path}: {exc}") from exc

    def prompt(self, prompt_id: str, **values: Any) -> tuple[str, str]:
        """按 ID 渲染提示词，并在调用模型前检查模板变量。"""

        try:
            item = self.prompts[prompt_id]
        except KeyError as exc:
            raise ConfigurationError(f"未知提示词 ID: {prompt_id}") from exc
        required = self._fields(item["system"]) | self._fields(item["user"])
        missing = required - values.keys()
        if missing:
            raise ConfigurationError(
                f"提示词 {prompt_id} 缺少变量: {', '.join(sorted(missing))}"
            )
        return item["system"].format(**values), item["user"].format(**values)

    def schema(self, format_id: str) -> dict[str, Any]:
        try:
            return self.formats[format_id]
        except KeyError as exc:
            raise ConfigurationError(f"未知数据格式 ID: {format_id}") from exc

    def validate(self, format_id: str, value: Any) -> list[str]:
        """使用统一数据格式校验任意中间结果。"""

        return [
            f"{error.message} (path: {list(error.path)})"
            for error in Draft202012Validator(self.schema(format_id)).iter_errors(value)
        ]

    def _validate_catalog(self) -> None:
        if self.prompt_document.get("version") != self.format_document.get("version"):
            raise ConfigurationError("prompt.json 与 data_formats.json 版本不一致")
        for prompt_id, item in self.prompts.items():
            if set(item) != {"system", "user"}:
                raise ConfigurationError(f"提示词 {prompt_id} 必须只有 system/user")
            self._fields(item["system"])
            self._fields(item["user"])
        for format_id, schema in self.formats.items():
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:
                raise ConfigurationError(
                    f"数据格式 {format_id} 不是有效 JSON Schema: {exc}"
                ) from exc

    @staticmethod
    def _fields(template: str) -> set[str]:
        try:
            return {
                field_name
                for _, field_name, _, _ in string.Formatter().parse(template)
                if field_name
            }
        except ValueError as exc:
            raise ConfigurationError(f"提示词模板格式错误: {exc}") from exc
