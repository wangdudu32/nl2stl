from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import KNOWLEDGE_DIR


class KnowledgeBase:
    """提供信号索引、详细定义、STL 算子和 AST Schema。"""

    _SCENE_ALIASES = {
        "AEB": ("aeb", "automatic emergency braking", "紧急制动", "自动紧急制动"),
        "ACC": ("acc", "adaptive cruise", "自适应巡航"),
        "Lane_Keeping": ("lane keeping", "lane departure", "车道保持", "车道偏离"),
        "Parking": ("parking", "park", "泊车", "停车"),
        "Traction_Control": ("traction control", "牵引力控制", "打滑"),
        "Traffic_Light": ("traffic light", "交通灯", "红灯", "绿灯", "黄灯"),
        "Speed_Limit": ("speed limit", "限速", "超速"),
        "Intersection": ("intersection", "路口", "交叉口"),
        "Pedestrian_and_Cyclist": ("pedestrian", "cyclist", "行人", "骑行者"),
        "Lane_Change": ("lane change", "blind spot", "变道", "盲区"),
    }
    _SIGNAL_ALIASES = {
        "ttc": ("time to collision", "碰撞时间"),
        "collision_warning": ("collision warning", "碰撞预警", "碰撞警告"),
        "brake_active": (
            "braking request",
            "brake request",
            "braking active",
            "制动请求",
            "请求制动",
            "制动动作",
        ),
        "front_vehicle_distance": (
            "distance to front vehicle",
            "following distance",
            "前车距离",
            "与前车应始终保持安全距离",
            "与前车保持安全距离",
        ),
        "acc_active": ("acc 跟车", "acc过程", "acc 过程中", "自适应巡航期间"),
        "ego_speed": ("ego speed", "vehicle speed", "自车速度", "车辆速度", "低速"),
    }

    def __init__(self) -> None:
        self.index = self._load_json(KNOWLEDGE_DIR / "signals_index.json")
        self.signals = self._load_json(KNOWLEDGE_DIR / "signals_explain.txt")
        self.operators = (KNOWLEDGE_DIR / "stl_operators.md").read_text(encoding="utf-8")
        raw_schema = (KNOWLEDGE_DIR / "ast_schema.txt").read_text(encoding="utf-8")
        self.ast_schema = json.loads(raw_schema[raw_schema.find("{") :])
        self._validate_index()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def compact_index(self) -> str:
        return json.dumps(self.index, ensure_ascii=False, separators=(",", ":"))

    def infer_selection(self, text: str) -> dict[str, Any] | None:
        """对文本中明确出现的场景和信号做高置信本地路由。"""

        normalized = " ".join(text.lower().replace("_", " ").split())
        domains = self.index.get("domains", {})
        if len(domains) != 1:
            return None
        domain, indexed_scenes = next(iter(domains.items()))

        explicit_scenes = [
            scene
            for scene, aliases in self._SCENE_ALIASES.items()
            if scene in indexed_scenes and any(alias in normalized for alias in aliases)
        ]
        matches: dict[str, set[str]] = {}
        for scene, scene_data in indexed_scenes.items():
            matched = {
                name
                for name in scene_data.get("signals", {})
                if self._mentions_signal(normalized, name)
            }
            matches[scene] = matched

        selected_scene: str | None = None
        if len(explicit_scenes) == 1:
            selected_scene = explicit_scenes[0]
        else:
            unique_signal_scenes = {
                scene
                for scene, names in matches.items()
                for name in names
                if sum(name in other for other in matches.values()) == 1
            }
            if len(unique_signal_scenes) == 1:
                selected_scene = next(iter(unique_signal_scenes))
            else:
                ranked = sorted(
                    ((len(names), scene) for scene, names in matches.items()), reverse=True
                )
                if ranked and ranked[0][0] >= 2 and (
                    len(ranked) == 1 or ranked[0][0] > ranked[1][0]
                ):
                    selected_scene = ranked[0][1]

        if selected_scene is None or not matches[selected_scene]:
            return None
        return {
            "domain": domain,
            "scenes": [selected_scene],
            "signals": sorted(matches[selected_scene]),
            "missing_concepts": [],
            "reason": "文本中的场景和信号可由本地索引唯一确定",
        }

    def _mentions_signal(self, text: str, name: str) -> bool:
        aliases = {name.lower(), name.lower().replace("_", " ")}
        aliases.update(self._SIGNAL_ALIASES.get(name, ()))
        return any(alias in text for alias in aliases)

    def signal_details(
        self, domain: str, scenes: list[str], names: list[str]
    ) -> dict[str, Any]:
        """只返回索引阶段选中的场景和信号，控制模型上下文规模。"""

        result: dict[str, Any] = {}
        domain_data = self.signals.get(domain, {})
        for scene in scenes:
            scene_data = domain_data.get(scene, {})
            selected = {
                name: scene_data[name]
                for name in names
                if name in scene_data
            }
            if selected:
                result[scene] = selected
        return result

    def all_signal_names(self) -> set[str]:
        return {
            name
            for scenes in self.signals.values()
            for signals in scenes.values()
            for name in signals
        }

    def validate_selection(self, selection: dict[str, Any]) -> list[str]:
        """阻止信号选择 Agent 引入索引中不存在的领域、场景或信号。"""

        errors: list[str] = []
        domain = selection.get("domain", "")
        scenes = selection.get("scenes", [])
        names = selection.get("signals", [])
        domain_data = self.signals.get(domain)
        if domain_data is None:
            return [f"知识库中不存在领域 {domain}"]
        available: set[str] = set()
        for scene in scenes:
            if scene not in domain_data:
                errors.append(f"领域 {domain} 中不存在场景 {scene}")
            else:
                available.update(domain_data[scene])
        unknown = set(names) - available
        if unknown:
            errors.append(f"所选场景中不存在信号: {', '.join(sorted(unknown))}")
        return errors

    def _validate_index(self) -> None:
        """启动时确认简短索引没有遗漏或虚构源文件中的信号。"""

        indexed = self.index.get("domains", {})
        for domain, scenes in self.signals.items():
            if domain not in indexed:
                raise ValueError(f"signals_index.json 缺少领域 {domain}")
            for scene, signals in scenes.items():
                got = indexed[domain].get(scene, {}).get("signals", {})
                if set(got) != set(signals):
                    raise ValueError(f"signals_index.json 与源文件不一致: {domain}/{scene}")
