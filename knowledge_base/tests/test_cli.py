from __future__ import annotations

import io

from stl_clarifier.cli import StatusLine


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
