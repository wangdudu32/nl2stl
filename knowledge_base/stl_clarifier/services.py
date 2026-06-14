from __future__ import annotations

import json
import re
from typing import TypeVar

import httpx
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ValidationError

from .config import Settings
from .schemas import SearchResult


SchemaT = TypeVar("SchemaT", bound=BaseModel)
MAX_GENERATION_ATTEMPTS = 3


class ExternalServiceError(RuntimeError):
    pass


class ChatAnywhereService:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_base_url:
            raise ExternalServiceError("OPENAI_BASE_URL 未配置")
        self.url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        timeout = settings.request_timeout_seconds
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(10, timeout), read=timeout, write=timeout),
            follow_redirects=True,
            trust_env=True,
        )

    def close(self) -> None:
        self.client.close()

    def generate(self, schema: type[SchemaT], system: str, user: str) -> SchemaT:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "{system}\n\n严格只输出一个 JSON 对象，不要使用 Markdown 代码块。"
                    "输出必须符合以下 JSON Schema：\n{schema_json}",
                ),
                ("human", "{user}"),
            ]
        )
        messages = prompt.format_messages(system=system, schema_json=schema_json, user=user)
        request_messages = [
            {
                "role": message.type if message.type != "human" else "user",
                "content": message.content,
            }
            for message in messages
        ]
        last_error: ValueError | ValidationError | KeyError | TypeError | None = None
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            payload = {
                "model": self.model,
                "temperature": 0,
                "messages": request_messages,
            }
            try:
                response = self.client.post(
                    self.url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                raw = response.json()
                content = raw["choices"][0]["message"]["content"]
            except httpx.TimeoutException as exc:
                raise ExternalServiceError("ChatAnywhere 请求超时") from exc
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:300]
                raise ExternalServiceError(
                    f"ChatAnywhere 返回 HTTP {exc.response.status_code}: {detail}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ExternalServiceError(f"ChatAnywhere 请求失败: {exc}") from exc
            except (KeyError, TypeError, ValueError) as exc:
                raise ExternalServiceError(f"ChatAnywhere 响应无效: {exc}") from exc

            try:
                return schema.model_validate_json(extract_json_object(content))
            except (ValueError, ValidationError, TypeError) as exc:
                last_error = exc
                if attempt == MAX_GENERATION_ATTEMPTS:
                    break
                request_messages.extend(
                    [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": _repair_instruction(exc, schema_json),
                        },
                    ]
                )

        raise ExternalServiceError(
            f"ChatAnywhere 响应连续 {MAX_GENERATION_ATTEMPTS} 次未通过结构校验: "
            f"{_validation_error_text(last_error)}"
        ) from last_error


class TavilyService:
    def __init__(self, api_key: str | None, timeout_seconds: float = 30) -> None:
        self.api_key = api_key
        self.client = httpx.Client(
            timeout=httpx.Timeout(
                timeout_seconds,
                connect=min(10, timeout_seconds),
                read=timeout_seconds,
                write=timeout_seconds,
            ),
            trust_env=True,
        )

    def close(self) -> None:
        self.client.close()

    def search(self, query: str) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            response = self.client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": 5,
                },
            )
            response.raise_for_status()
            raw = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        results: list[SearchResult] = []
        for item in raw.get("results", []):
            if isinstance(item, dict) and item.get("url"):
                results.append(
                    SearchResult(
                        title=str(item.get("title", "")),
                        url=str(item["url"]),
                        content=str(item.get("content", "")),
                    )
                )
        return results


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    if start < 0:
        raise ValueError("响应中没有 JSON 对象")
    _, end = json.JSONDecoder().raw_decode(stripped[start:])
    return stripped[start : start + end]


def _repair_instruction(error: Exception, schema_json: str) -> str:
    return (
        "上一条响应未通过结构校验。请保持原有分析结论和候选内容不变，"
        "只修正字段名、字段类型、枚举值、缺失字段或 JSON 格式，并重新输出完整 JSON 对象。"
        "不要解释，不要使用 Markdown。\n\n"
        f"校验错误：\n{_validation_error_text(error)}\n\n"
        f"目标 JSON Schema：\n{schema_json}"
    )


def _validation_error_text(error: Exception | None) -> str:
    if isinstance(error, ValidationError):
        details = []
        for item in error.errors(include_url=False):
            location = ".".join(str(part) for part in item["loc"])
            details.append(f"{location}: {item['msg']}；收到 {item.get('input')!r}")
        return "\n".join(details)
    return str(error or "未知结构错误")
