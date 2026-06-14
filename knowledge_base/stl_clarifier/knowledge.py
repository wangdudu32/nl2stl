from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalEvidence:
    context: str
    source_ids: list[str]


class KnowledgeBase:
    def __init__(self, signals_path: Path, operators_path: Path) -> None:
        self.signals_path = signals_path
        self.operators_path = operators_path
        raw_signals = json.loads(signals_path.read_text(encoding="utf-8"))
        self.signals = self._flatten_signals(raw_signals)
        self.signal_source_name = signals_path.name
        self.operators_text = operators_path.read_text(encoding="utf-8")

    def retrieve(self, request: str, query: str, limit: int = 12) -> LocalEvidence:
        tokens = self._tokens(f"{request} {query}")
        ranked: list[tuple[int, str, str]] = []
        for path, description in self.signals.items():
            local_name = path.rsplit("/", 1)[-1]
            haystack = f"{path} {description}".lower()
            score = sum(3 if token in path.lower() else 1 for token in tokens if token in haystack)
            if score:
                ranked.append((score, path, description))
        ranked.sort(key=lambda item: (-item[0], item[1]))

        blocks: list[str] = []
        source_ids: list[str] = []
        for _, path, description in ranked[:limit]:
            local_name = path.rsplit("/", 1)[-1]
            source_id = f"{self.signal_source_name}#{path}"
            source_ids.append(source_id)
            blocks.append(
                f"[{source_id}] 信号名={local_name}；场景路径={path}；{description}"
            )

        operator_sections = self._operator_sections(tokens)
        for title, body in operator_sections[:5]:
            source_id = f"stl_operators.md#{title}"
            source_ids.append(source_id)
            blocks.append(f"[{source_id}]\n{body}")

        return LocalEvidence(context="\n\n".join(blocks), source_ids=source_ids)

    def signal_names(self) -> set[str]:
        return {path.rsplit("/", 1)[-1] for path in self.signals}

    def signal_units(self, scenes: list[str] | None = None) -> dict[str, str]:
        normalized = {scene.lower() for scene in scenes or []}
        units: dict[str, str] = {}
        for path, description in self.signals.items():
            if normalized and not any(f"/{scene}/" in path.lower() for scene in normalized):
                continue
            name = path.rsplit("/", 1)[-1]
            if "布尔" in description or "取值 0/1" in description:
                unit = "boolean"
            elif "无量纲" in description:
                unit = "dimensionless"
            else:
                unit_matches = re.findall(
                    r"单位\s*(?:均?为\s*)?"
                    r"(km/h|m/s\^2|m/s|degree/s|degree|N\*m|ms|s|m|%|count)",
                    description,
                    flags=re.IGNORECASE,
                )
                unit = unit_matches[-1] if unit_matches else "unknown"
            existing = units.get(name)
            if existing is None or existing == unit:
                units[name] = unit
            else:
                units[name] = "unknown"
        return units

    def retrieve_for_scenes(
        self,
        request: str,
        query: str,
        scenes: list[str],
        limit: int = 12,
    ) -> LocalEvidence:
        evidence = self.retrieve(request, query, limit=max(limit * 3, 24))
        normalized = {scene.lower() for scene in scenes}
        if not normalized:
            return evidence
        selected_ids = [
            source_id
            for source_id in evidence.source_ids
            if source_id.startswith("stl_operators.md#")
            or any(f"/{scene}/" in source_id.lower() for scene in normalized)
        ][:limit]
        blocks = []
        for block in evidence.context.split("\n\n"):
            if any(f"[{source_id}]" in block for source_id in selected_ids):
                blocks.append(block)
        return LocalEvidence(context="\n\n".join(blocks), source_ids=selected_ids)

    @classmethod
    def _flatten_signals(
        cls, node: object, path: tuple[str, ...] = ()
    ) -> dict[str, str]:
        if isinstance(node, str):
            if not path:
                raise ValueError("信号知识库的字符串叶子缺少名称路径")
            return {"/".join(path): node}
        if not isinstance(node, dict):
            location = "_".join(path) or "<root>"
            raise ValueError(f"信号知识库 {location} 必须是对象或字符串")

        flattened: dict[str, str] = {}
        for key, value in node.items():
            if not isinstance(key, str) or not key:
                raise ValueError("信号知识库包含无效键名")
            flattened.update(cls._flatten_signals(value, (*path, key)))
        return flattened

    @staticmethod
    def _tokens(text: str) -> set[str]:
        english = re.findall(r"[a-zA-Z][a-zA-Z0-9_]+", text.lower())
        chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        expanded: set[str] = set(english + chinese)
        aliases = {
            "泊车": ["parking"],
            "停车": ["parking"],
            "牵引力": ["traction", "tcs"],
            "油门": ["throttle"],
            "刹车": ["brake_active", "aeb_active", "brake"],
            "制动": ["brake_active", "aeb_active", "brake"],
            "速度": ["speed"],
            "自车速度": ["ego_speed"],
            "限速": ["speed_limit", "speeding_margin"],
            "道路限速": ["speed_limit"],
            "前车": ["front_vehicle"],
            "距离": ["distance"],
            "跟车": ["acc"],
            "始终": ["always"],
            "最终": ["eventually"],
            "直到": ["until"],
            "过去": ["once", "historically", "since"],
        }
        for key, values in aliases.items():
            if key in text:
                expanded.update(values)
        return {token for token in expanded if len(token) > 1}

    def _operator_sections(self, tokens: set[str]) -> list[tuple[str, str]]:
        sections = re.split(r"(?=^######\s+)", self.operators_text, flags=re.MULTILINE)
        matches: list[tuple[str, str]] = []
        for section in sections:
            heading = re.match(r"^######\s+(.+)$", section, flags=re.MULTILINE)
            if not heading:
                continue
            title = heading.group(1).strip()
            score = sum(1 for token in tokens if token.lower() in section.lower())
            if score:
                matches.append((title, section.strip()))
        return matches
