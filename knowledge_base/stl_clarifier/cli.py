from __future__ import annotations

import argparse
import sys

from .config import Settings
from .knowledge import KnowledgeBase
from .schemas import Ambiguity, Candidate
from .services import ChatAnywhereService, ExternalServiceError, TavilyService
from .workflow import ClarificationWorkflow


SOURCE_LABELS = {
    "signal_knowledge": "信号知识库",
    "stl_knowledge": "STL算子知识库",
    "tavily": "Tavily检索",
    "llm_inference": "LLM推断",
    "user_input": "用户输入",
}


class StatusLine:
    def __init__(self) -> None:
        self.enabled = sys.stdout.isatty()
        self.visible = False

    def update(self, message: str) -> None:
        if not self.enabled:
            return
        text = self._user_facing_message(message)
        if not text:
            self.clear()
            return
        sys.stdout.write(f"\r\033[2K{text}")
        sys.stdout.flush()
        self.visible = True

    def clear(self) -> None:
        if self.enabled and self.visible:
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
        self.visible = False

    @staticmethod
    def _user_facing_message(message: str) -> str:
        if "Tavily" in message and "检索" in message and "完成" not in message:
            return "正在搜索相关资料..."
        if "相关性" in message and "正在" in message:
            return "正在筛选相关资料..."
        if "生成" in message and "公式" in message and "完成" not in message:
            return "正在生成 STL 公式..."
        if "生成" in message and "候选" in message and "完成" not in message:
            return "正在生成候选项..."
        if "校验自定义回答" in message and "完成" not in message:
            return "正在判断你的回答是否充分..."
        if "分析" in message and "完成" not in message:
            return "正在分析需求..."
        if "正在" in message and "完成" not in message:
            return "正在处理..."
        return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="逐步澄清自然语言并生成 STL 公式")
    parser.add_argument("description", nargs="?", help="待翻译的自然语言描述")
    return parser.parse_args()


def ask_user(
    ambiguity: Ambiguity, candidates: list[Candidate], status: StatusLine | None = None
) -> str:
    if status:
        status.clear()
    issue_label = "模糊点" if ambiguity.issue_type == "vagueness" else "歧义点"
    print(f"\n{issue_label}：{ambiguity.description}")
    print(ambiguity.question)
    for index, candidate in enumerate(candidates, start=1):
        label = SOURCE_LABELS.get(candidate.source_type.value, candidate.source_type.value)
        parameter_text = (
            f"；参数：{', '.join(candidate.parameters)}" if candidate.parameters else ""
        )
        print(
            f"{index}. {candidate.value}：{candidate.explanation} "
            f"[{label}：{candidate.source_reference}{parameter_text}]"
        )
    print(f"{len(candidates) + 1}. 自行输入其他澄清值或解释")
    answer = input("请选择编号，或直接输入自定义澄清：").strip()
    if answer == str(len(candidates) + 1):
        return input("请输入你的自定义澄清：").strip()
    return answer


def run() -> None:
    args = parse_args()
    settings = Settings.load()
    description = args.description or input("请输入自然语言需求：").strip()
    if not description:
        raise SystemExit("自然语言需求不能为空")

    status = StatusLine()

    workflow = ClarificationWorkflow(
        ChatAnywhereService(settings),
        TavilyService(settings.tavily_api_key, settings.request_timeout_seconds),
        KnowledgeBase(settings.signals_path, settings.operators_path),
        status.update,
    )
    try:
        result, errors = workflow.run(
            description,
            lambda ambiguity, candidates: ask_user(ambiguity, candidates, status),
        )
    finally:
        status.clear()
        workflow.close()

    print("\n清晰描述：")
    print(result.clarified_description)
    print("\nSTL 公式：")
    print(result.formula)
    print("\n说明：")
    print(result.explanation)
    if errors:
        print("\n校验警告：")
        for error in errors:
            print(f"- {error}")


def main() -> None:
    try:
        run()
    except KeyboardInterrupt:
        raise SystemExit("\n已取消") from None
    except ExternalServiceError as exc:
        raise SystemExit(f"外部服务调用失败：{exc}") from None
    except RuntimeError as exc:
        raise SystemExit(f"候选生成或公式生成失败：{exc}") from None
    except EOFError:
        raise SystemExit("未读取到交互输入。请在终端中运行，或提供完整输入。") from None


if __name__ == "__main__":
    main()
