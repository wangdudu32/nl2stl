from __future__ import annotations

import json

import httpx
import pytest

from stl_clarifier.schemas import AmbiguityAnalysis
from stl_clarifier.services import ChatAnywhereService, ExternalServiceError


class FakeClient:
    def __init__(self, contents: list[str]) -> None:
        self.contents = iter(contents)
        self.payloads: list[dict] = []

    def post(self, url, headers, json):
        self.payloads.append(json)
        content = next(self.contents)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": content}}]},
        )


def build_service(contents: list[str]) -> tuple[ChatAnywhereService, FakeClient]:
    service = ChatAnywhereService.__new__(ChatAnywhereService)
    service.url = "https://example.com/chat/completions"
    service.api_key = "test"
    service.model = "test-model"
    client = FakeClient(contents)
    service.client = client
    return service, client


def valid_analysis() -> str:
    return json.dumps(
        {
            "context": {
                "domain": "自动驾驶",
                "scene": "泊车",
                "subject": "自车",
                "quantities": ["速度"],
                "expected_units": ["km/h"],
                "search_keywords": ["泊车"],
                "knowledge_scenes": ["Parking"],
            },
            "ambiguities": [
                {
                    "id": "scope",
                    "issue_type": "ambiguity",
                    "description": "泊车过程范围不明确",
                    "question": "如何界定泊车过程？",
                    "category": "scope",
                    "knowledge_query": "parking scope",
                }
            ],
        },
        ensure_ascii=False,
    )


def invalid_analysis() -> str:
    data = json.loads(valid_analysis())
    data["ambiguities"][0]["issue_type"] = "scope"
    return json.dumps(data, ensure_ascii=False)


def test_generate_retries_with_validation_feedback_then_succeeds() -> None:
    service, client = build_service([invalid_analysis(), valid_analysis()])

    result = service.generate(AmbiguityAnalysis, "分析需求", "原始需求")

    assert result.ambiguities[0].issue_type == "ambiguity"
    assert len(client.payloads) == 2
    repair_message = client.payloads[1]["messages"][-1]["content"]
    assert "ambiguities.0.issue_type" in repair_message
    assert "只修正字段名" in repair_message
    assert client.payloads[1]["messages"][-2] == {
        "role": "assistant",
        "content": invalid_analysis(),
    }


def test_generate_stops_after_three_invalid_responses() -> None:
    service, client = build_service([invalid_analysis()] * 3)

    with pytest.raises(ExternalServiceError, match="连续 3 次未通过结构校验"):
        service.generate(AmbiguityAnalysis, "分析需求", "原始需求")

    assert len(client.payloads) == 3
