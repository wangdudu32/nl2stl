from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx
from jsonschema import Draft202012Validator
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

from .config import RuntimeCatalog, Settings


class ExternalServiceError(RuntimeError):
    pass


class StructuredLLM:
    """封装 ChatAnywhere 的结构化调用、格式验证和有限重试。"""

    def __init__(
        self,
        settings: Settings,
        catalog: RuntimeCatalog,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.catalog = catalog
        self.max_attempts = settings.max_llm_attempts
        self.progress = progress or (lambda _message: None)
        timeout = httpx.Timeout(
            settings.timeout_seconds,
            connect=min(10, settings.timeout_seconds),
            read=settings.timeout_seconds,
            write=settings.timeout_seconds,
            pool=min(10, settings.timeout_seconds),
        )
        self.http_client = httpx.Client(timeout=timeout, trust_env=True)
        self.native_json_schema = "chatanywhere" not in settings.base_url.lower()
        self.model = ChatOpenAI(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=0,
            timeout=settings.timeout_seconds,
            max_retries=1,
            http_client=self.http_client,
            http_socket_options=(),
        )

    def invoke(
        self,
        prompt_id: str,
        format_id: str | None = None,
        output_schema: dict[str, Any] | None = None,
        **values: Any,
    ) -> dict[str, Any]:
        """调用指定 Agent，并确保结果满足统一管理的 JSON Schema。"""

        schema = output_schema or self.catalog.schema(format_id or "")
        system, user = self.catalog.prompt(prompt_id, **values)
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self._structured_call(system, user, schema)
                if not isinstance(result, dict):
                    raise TypeError("模型没有返回 JSON 对象")
                errors = list(Draft202012Validator(schema).iter_errors(result))
                if errors:
                    raise ValueError("; ".join(error.message for error in errors))
                return result
            except Exception as exc:  # Network and structured-output errors share retry policy.
                last_error = exc
                if attempt < self.max_attempts:
                    self.progress(
                        f"模型响应无效，正在重试（{attempt + 1}/{self.max_attempts}）..."
                    )
                    time.sleep(min(2 ** (attempt - 1), 4))
        raise ExternalServiceError(
            f"ChatAnywhere 调用连续 {self.max_attempts} 次失败: {last_error}"
        )

    def _structured_call(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """优先使用原生结构化输出，不兼容时退回 JSON 文本模式。"""

        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        if self.native_json_schema:
            try:
                runnable = self.model.with_structured_output(schema, method="json_schema")
                result = runnable.invoke(messages)
                if isinstance(result, dict):
                    return result
            except Exception:
                # Fall back when an OpenAI-compatible gateway lacks native JSON Schema.
                pass
        schema_text = json.dumps(schema, ensure_ascii=False)
        fallback_messages = [
            SystemMessage(
                content=(
                    system
                    + "\n\n严格只输出一个 JSON 对象，不要使用 Markdown。"
                    + "输出必须符合以下 JSON Schema：\n"
                    + schema_text
                )
            ),
            HumanMessage(content=user),
        ]
        response = self.model.invoke(fallback_messages)
        content = response.content
        if not isinstance(content, str):
            raise TypeError("模型响应内容不是文本")
        return _extract_json_object(content)


class TavilyService:
    """通过 LangChain Tavily 工具提供可降级的外部检索。"""

    def __init__(
        self,
        settings: Settings,
        catalog: RuntimeCatalog,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.catalog = catalog
        self.progress = progress or (lambda _message: None)
        self.available = bool(settings.tavily_api_key)
        self.tool = (
            TavilySearch(max_results=5, search_depth="advanced", topic="general")
            if self.available
            else None
        )

    def search(self, query: str) -> list[dict[str, str]]:
        """搜索并规范化结果；网络或格式异常时返回空结果以便降级。"""

        if self.tool is None:
            return []
        try:
            raw = self.tool.invoke({"query": query})
        except Exception:
            self.progress("Tavily 搜索失败，正在使用本地知识与 LLM 候选...")
            return []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return []
        items = raw.get("results", []) if isinstance(raw, dict) else raw
        results = [
            {
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
                "content": str(item.get("content", item.get("snippet", "")))[:3000],
            }
            for item in items or []
            if isinstance(item, dict) and item.get("url")
        ]
        schema = self.catalog.schema("search_results")
        return results if Draft202012Validator(schema).is_valid(results) else []


def _extract_json_object(text: str) -> dict[str, Any]:
    """从兼容网关的纯文本响应中提取第一个 JSON 对象。"""

    stripped = text.strip()
    start = stripped.find("{")
    if start < 0:
        raise ValueError("响应中没有 JSON 对象")
    value, _ = json.JSONDecoder().raw_decode(stripped[start:])
    if not isinstance(value, dict):
        raise TypeError("响应 JSON 不是对象")
    return value
