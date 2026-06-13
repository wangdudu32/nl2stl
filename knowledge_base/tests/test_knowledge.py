from pathlib import Path

from stl_clarifier.knowledge import KnowledgeBase


ROOT = Path(__file__).resolve().parents[1]


def test_loads_signal_dictionary() -> None:
    kb = KnowledgeBase(ROOT / "signals_kb.txt", ROOT / "stl_operators.md")
    assert len(kb.signals) == 106
    assert "ego_speed" in kb.signal_names()
    assert "parking_mode" in kb.signal_names()


def test_retrieves_parking_speed_and_always_operator() -> None:
    kb = KnowledgeBase(ROOT / "signals_kb.txt", ROOT / "stl_operators.md")
    evidence = kb.retrieve("整个泊车过程中车辆应始终保持低速", "泊车速度和始终算子")
    assert "信号名=ego_speed" in evidence.context
    assert "signals_kb.txt#Autonomous_Driving/Parking/ego_speed" in evidence.context
    assert "always" in evidence.context.lower()


def test_parking_alias_matches_parking_scene() -> None:
    kb = KnowledgeBase(ROOT / "signals_kb.txt", ROOT / "stl_operators.md")
    evidence = kb.retrieve("在整个停车过程中", "停车过程状态")
    assert "signals_kb.txt#Autonomous_Driving/Parking/parking_mode" in evidence.source_ids


def test_speed_limit_request_retrieves_dynamic_limit_signals() -> None:
    kb = KnowledgeBase(ROOT / "signals_kb.txt", ROOT / "stl_operators.md")
    evidence = kb.retrieve("车辆始终不得超过限速", "车辆道路限速")
    assert "signals_kb.txt#Autonomous_Driving/Speed_Limit/speed_limit" in evidence.source_ids
    assert "signals_kb.txt#Autonomous_Driving/Speed_Limit/ego_speed" in evidence.source_ids
