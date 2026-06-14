from __future__ import annotations

import io

from stl_clarifier.cli import InteractionPage, StatusLine
from stl_clarifier.schemas import (
    Ambiguity,
    Candidate,
    Clarification,
    SourceType,
    STLResult,
    TranslationFragment,
)


def test_status_line_maps_internal_progress_to_short_user_message() -> None:
    assert (
        StatusLine._user_facing_message(
            "1/4 正在调用 ChatAnywhere 分析领域、场景和歧义"
        )
        == "正在分析需求..."
    )
    assert (
        StatusLine._user_facing_message("2/4 本地知识不足，正在使用 Tavily 检索")
        == "正在搜索相关资料..."
    )


def test_status_line_hides_completion_and_internal_diagnostics() -> None:
    assert StatusLine._user_facing_message("1/4 完成，用时 2.5 秒") == ""
    assert StatusLine._user_facing_message("识别结果：领域=自动驾驶") == ""
    assert StatusLine._user_facing_message("已拒绝不可执行的搜索候选") == ""


def test_status_line_clears_finished_message(monkeypatch) -> None:
    output = io.StringIO()
    monkeypatch.setattr("stl_clarifier.cli.sys.stdout", output)

    status = StatusLine()
    status.enabled = True
    status.update("正在调用 ChatAnywhere 生成候选项")
    status.update("生成候选项 完成，用时 1.0 秒")

    assert "正在生成候选项..." in output.getvalue()
    assert output.getvalue().endswith("\r\033[2K")
    assert status.visible is False


def test_interaction_page_renders_compact_progress_and_partial_mapping(
    monkeypatch,
) -> None:
    output = io.StringIO()
    monkeypatch.setattr("stl_clarifier.cli.sys.stdout", output)
    page = InteractionPage()
    page.enabled = False
    current = Ambiguity(
        id="scope",
        description="泊车过程尚未映射为可观测条件",
        question="如何界定泊车过程？",
        category="scope",
        knowledge_query="parking scope",
    )
    resolved = Clarification(
        ambiguity_id="speed",
        ambiguity_description="“低速”缺少量化定义",
        issue_type="vagueness",
        category="threshold",
        question="低速是多少？",
        answer="ego_speed <= 5 km/h",
        source_type=SourceType.LLM_INFERENCE,
        source_reference="不应显示的内部来源",
    )
    candidate = Candidate(
        id="parking_mode",
        value="在 parking_mode == 1 期间",
        explanation="使用泊车状态",
        source_type=SourceType.SIGNAL_KNOWLEDGE,
        source_reference="signals_kb.txt#Parking/parking_mode",
    )
    page.update([current], [resolved])

    page.render_question(current, [candidate])

    text = output.getvalue()
    assert "待澄清的模糊点" in text
    assert "已澄清的模糊点" in text
    assert "低速：ego_speed <= 5 km/h" in text
    assert "“低速”\n-> ego_speed <= 5" in text
    assert "不应显示的内部来源" not in text


def test_interaction_page_renders_structured_final_mappings(monkeypatch) -> None:
    output = io.StringIO()
    monkeypatch.setattr("stl_clarifier.cli.sys.stdout", output)
    page = InteractionPage()
    page.enabled = False
    result = STLResult(
        clarified_description="泊车期间自车速度始终不超过 5 km/h",
        formula="always((parking_mode == 1) -> (ego_speed <= 5))",
        explanation="使用泊车状态限定作用范围。",
        signals_used=["parking_mode", "ego_speed"],
        fragment_mappings=[
            TranslationFragment(
                nl_fragment="泊车期间", stl_fragment="parking_mode == 1"
            ),
            TranslationFragment(
                nl_fragment="自车速度不超过 5 km/h",
                stl_fragment="ego_speed <= 5",
            ),
        ],
    )

    page.render_result(result, [])

    text = output.getvalue()
    assert "“泊车期间”\n-> parking_mode == 1" in text
    assert "“自车速度不超过 5 km/h”\n-> ego_speed <= 5" in text
