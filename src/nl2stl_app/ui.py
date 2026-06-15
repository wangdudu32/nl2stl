from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any


SOURCE_LABELS = {
    "knowledge_base": "知识库",
    "search": "Tavily 搜索",
    "llm_generated": "LLM 生成",
}


class TerminalUI:
    """只保留当前页面，并实时显示长耗时步骤。"""

    def __init__(self) -> None:
        self.interactive = sys.stdout.isatty()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._step = ""
        self._step_started = 0.0
        self._last_printed = ""

    def update_step(self, message: str) -> None:
        """供 LangGraph 节点和服务重试实时更新当前执行步骤。"""

        if not message:
            self.clear_step()
            return
        if not self.interactive:
            if message != self._last_printed:
                print(f"当前步骤：{message}", flush=True)
                self._last_printed = message
            return

        with self._lock:
            self._step = message
            self._step_started = time.monotonic()
        self._write_step()
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._refresh_step, daemon=True)
            self._thread.start()

    def clear_step(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.3)
        self._thread = None
        if self.interactive and self._step:
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
        self._step = ""

    def close(self) -> None:
        self.clear_step()

    def clear(self) -> None:
        self.clear_step()
        if self.interactive:
            os.system("clear")

    def render_interrupt(self, payload: dict[str, Any]) -> str:
        self.clear()
        ambiguity = payload["ambiguity"]
        semantics = payload.get("global_semantics", {})
        print("当前阶段：需求澄清")
        print("\n未澄清")
        for item in semantics.get("ambiguities", [ambiguity]):
            print(f"- {item['description']}")

        print("\n已澄清（当前全局语义）")
        resolved = [
            item
            for item in semantics.get("items", [])
            if item.get("status") == "resolved"
        ]
        if resolved:
            for item in resolved:
                print(f"- {item['nl_fragment']} → {item['value']}")
        else:
            print("- 无")

        print("\nSTL 与 NL 对应片段")
        mappings = semantics.get("mappings", [])
        if mappings:
            for item in mappings:
                print(f"- {item['nl_fragment']} → {item['stl_fragment']}")
        else:
            print(f"- {ambiguity['nl_fragment']} → 待澄清")

        feedback = payload.get("feedback")
        if feedback:
            print(f"\n上一输入未通过一致性验证：{feedback}")

        print(f"\n{ambiguity['question']}")
        for index, candidate in enumerate(payload["candidates"]):
            label = chr(ord("A") + index)
            source = SOURCE_LABELS.get(candidate["source_type"], candidate["source_type"])
            print(f"{label}. {candidate['value']}")
            print(f"   {_compact(candidate['explanation'], 72)}")
            print(f"   来源：{source}（{_compact(candidate['source_reference'], 96)}）")
        custom_label = chr(ord("A") + len(payload["candidates"]))
        print(f"{custom_label}. 自定义澄清（自然语言、数值、单位、区间或公式）")

        answer = input("\n请选择候选或直接输入：").strip()
        if answer.upper() == custom_label:
            return input("请输入自定义澄清：").strip()
        return answer

    def render_result(self, state: dict[str, Any]) -> None:
        self.clear()
        result = state.get("result", {})
        if state.get("status") != "complete":
            print("当前阶段：验证失败")
            for error in result.get("errors", ["未知错误"]):
                print(f"- {error}")
            return

        semantics = result["global_semantics"]
        print("当前阶段：完成")
        print("\n未澄清\n- 无")
        print("\n已澄清（最终全局语义）")
        resolved = [
            item for item in semantics.get("items", []) if item.get("status") == "resolved"
        ]
        if resolved:
            for item in resolved:
                print(f"- {item['nl_fragment']} → {item['value']}")
        else:
            print("- 原始描述已足够明确")
        print("\nSTL 与 NL 对应片段")
        for item in result["mappings"]:
            print(f"- {item['nl_fragment']} → {item['stl_fragment']}")
        print("\n最终 STL")
        print(result["stl"])
        print(f"\nAST：{result['ast_path']}")
        print(f"验证：{result['schema_validation']}")

    def _refresh_step(self) -> None:
        while not self._stop.wait(0.2):
            self._write_step()

    def _write_step(self) -> None:
        with self._lock:
            message = self._step
            elapsed = int(time.monotonic() - self._step_started)
        if message:
            sys.stdout.write(f"\r\033[2K当前步骤：{message}（{elapsed}s）")
            sys.stdout.flush()


def _compact(value: str, limit: int) -> str:
    """候选页只展示首句和必要来源信息。"""

    text = " ".join(str(value).split())
    for separator in ("。", ";", "；", "\n"):
        if separator in text:
            text = text.split(separator, 1)[0]
            break
    return text if len(text) <= limit else text[: limit - 1] + "…"
