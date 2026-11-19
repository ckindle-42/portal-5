"""J1: the two stale Jarvis operator sentences stay corrected."""

from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def test_runbook_escalation_is_not_described_as_enabled() -> None:
    text = (_REPO / "docs" / "JARVIS_LOCAL_RUNBOOK.md").read_text(encoding="utf-8")
    assert "Enabled (10-30" not in text
    assert "escalation.enabled" in text
    assert "false" in text
    assert "telegram_control" in text


def test_operators_guide_does_not_call_detection_engineering_unseated() -> None:
    text = (_REPO / "docs" / "ORCHESTRATION_ARM_OPERATORS.md").read_text(encoding="utf-8")
    assert "unseated candidate" not in text
    assert "seating_status: seated" in text
