"""Hermetic tests for the platform agent core. No network, no live pipeline."""

from __future__ import annotations

from typing import Any

from portal.platform.agent import (
    Goal,
    select_tools,
    validate_goal,
)


def _goal(**kw: Any) -> Goal:
    base: dict[str, Any] = {
        "intent": "poke the box",
        "scope": {"targets": ["10.10.11.5"]},
        "budget": {"max_iterations": 5, "max_wall_clock_sec": 0, "max_lab_actions": 5},
        "stop_when": [{"observation": "owned", "equals": True}],
        "domain_hint": "ad",
    }
    base.update(kw)
    return Goal(**base)


def test_validate_goal_rejects_unbounded() -> None:
    assert "scope.targets is empty or missing" in validate_goal(Goal(intent="x"))
    assert any("budget" in p for p in validate_goal(Goal(intent="x", scope={"targets": ["a"]})))
    assert validate_goal(_goal()) == []


def test_select_tools_initial_coverage() -> None:
    cands = select_tools({}, ["a", "b", "c", "d"])
    assert [c.name for c in cands] == ["a", "b", "c"]
