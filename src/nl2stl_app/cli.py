from __future__ import annotations

import argparse
from typing import Any

from langgraph.types import Command

from .graph import build_graph, initial_state
from .ui import TerminalUI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="交互式自然语言到 STL 翻译器")
    parser.add_argument("description", nargs="?", help="待翻译的自然语言描述")
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    text = args.description or input("请输入自然语言需求：").strip()
    if not text:
        raise SystemExit("自然语言需求不能为空")

    ui = TerminalUI()
    graph = build_graph(progress=ui.update_step)
    state = initial_state(text)
    config = {"configurable": {"thread_id": state["session_id"]}}
    command: dict[str, Any] | Command = state

    try:
        ui.update_step("正在启动翻译流程...")
        while True:
            output = graph.invoke(command, config=config)
            interrupts = output.get("__interrupt__", [])
            if interrupts:
                answer = ui.render_interrupt(interrupts[0].value)
                command = Command(resume=answer)
                continue
            ui.render_result(output)
            return
    finally:
        ui.close()


def main() -> None:
    try:
        run()
    except KeyboardInterrupt:
        raise SystemExit("\n已取消") from None
    except EOFError:
        raise SystemExit("未读取到交互输入") from None
    except Exception as exc:
        raise SystemExit(f"运行失败：{exc}") from None


if __name__ == "__main__":
    main()
