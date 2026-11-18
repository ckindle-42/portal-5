"""Offline tests for planner, reviewer, Telegram and calibration contracts."""

from __future__ import annotations

from typing import Any

import pytest

from portal.modules.orchestration.calibration import calibration_status, project_remaining
from portal.modules.orchestration.contracts import parse_plan
from portal.modules.orchestration.planner import (
    PLANNER_RULES,
)
from portal.modules.orchestration.service import _require_calibration


def test_planner_prompt_includes_required_decomposition_rules() -> None:
    assert "deterministic acceptance check" in PLANNER_RULES
    assert "accept" in PLANNER_RULES
    assert "finish call" in PLANNER_RULES
    assert "file_write is only for additional write_paths" in PLANNER_RULES
    assert "Split reading from acting" in PLANNER_RULES
    assert "stage='assembly' followed by stage='final_review'" in PLANNER_RULES


def test_calibration_projects_remaining_probability_cost_and_pause() -> None:
    plan = parse_plan(
        {
            "task_id": "calibration",
            "goal": "check calibration",
            "bites": [_raw_bite("first", "fast"), _raw_bite("second", "deep")],
        }
    )
    rates = {
        "test_fixing": {
            "fast": {"pass_probability": 0.8, "mean_seconds": 4},
            "deep": {"pass_probability": 0.9, "mean_seconds": 5},
        }
    }
    projection = project_remaining(plan.bites, {"first"}, rates)
    assert projection.pass_probability == pytest.approx(0.9)
    assert projection.expected_seconds == pytest.approx(5)
    policy = {"minimum_pass_probability": 0.95, "rates_by_discipline": rates}
    projected, pause = calibration_status(policy, plan, {"first"})
    assert projected == projection and pause


def test_unattended_run_refuses_null_gate_c_threshold() -> None:
    with pytest.raises(ValueError, match="unattended runs are disabled"):
        _require_calibration({"calibration": {"minimum_pass_probability": None}}, True)
    _require_calibration({"calibration": {"minimum_pass_probability": None}}, False)


@pytest.mark.parametrize("threshold", [0.0, -0.5, "0.9"])
def test_unattended_run_refuses_disabled_gate_c_threshold(threshold: Any) -> None:
    """N6: a non-positive or non-numeric threshold disables calibration, like null."""
    policy = {"calibration": {"minimum_pass_probability": threshold}}
    with pytest.raises(ValueError, match="unattended runs are disabled"):
        _require_calibration(policy, True)
    _require_calibration(policy, False)


def test_unattended_run_accepts_a_positive_gate_c_threshold() -> None:
    """N6: the refusal is specific to disabled thresholds, not every value."""
    rates = {
        "test_fixing": {
            "fast": {"pass_probability": 0.8, "mean_seconds": 1},
            "deep": {"pass_probability": 0.9, "mean_seconds": 1},
        }
    }
    _require_calibration(
        {"calibration": {"minimum_pass_probability": 0.01, "rates_by_discipline": rates}},
        True,
        {"test_fixing"},
    )


@pytest.mark.parametrize("control", ["\n", "\r", "\t", "\x00", "\x85"])
def test_plan_rejects_control_characters_in_bite_id(control: str) -> None:
    raw = _raw_bite("bite", "fast")
    raw["bite_id"] = f"bite{control}forged"
    with pytest.raises(ValueError, match="bite_id must not contain control characters"):
        parse_plan({"task_id": "control-check", "goal": "Check output", "bites": [raw]})


def _raw_bite(
    bite_id: str,
    model: str,
    *,
    stage: str = "work",
    tools: list[str] | None = None,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "bite_id": bite_id,
        "goal": f"Complete {bite_id}.",
        "discipline": "test_fixing",
        "inputs": [],
        **({"write_paths": ["artifact.txt"]} if "file_write" in (tools or []) else {}),
        "depends_on": depends_on or [],
        "tools": tools or [],
        "output": {"path": f"bites/{bite_id}.txt", "file_type": "text"},
        "accept": [{"type": "contains", "value": "done"}],
        "risk": "low",
        "stage": stage,
        "budget": {"turns": 2, "minutes": 2, "output_tokens": 128, "context_tokens": 512},
        "model": model,
        "procedure": "Use only the selected tool group.",
    }
