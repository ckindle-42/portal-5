"""Goal — bounded, open-ended alternative to a fixed playbook path.

Promoted from portal.modules.security.core.goal (role removed; security
subclasses to re-add role/targets). Open-ended does NOT mean unbounded: a Goal
without scope or budget is invalid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_REQUIRED_BUDGET_KEYS = ("max_iterations", "max_wall_clock_sec", "max_lab_actions")


@dataclass
class Goal:
    intent: str
    scope: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    stop_when: list[dict] | None = None
    domain_hint: str | None = None


def validate_goal(goal: Goal) -> list[str]:
    """Reject a goal with no scope.targets or no budget. Nothing runs unbounded."""
    problems: list[str] = []

    if not goal.scope or not goal.scope.get("targets"):
        problems.append("scope.targets is empty or missing")

    if not goal.budget:
        problems.append("missing budget")
    else:
        for bk in _REQUIRED_BUDGET_KEYS:
            if bk not in goal.budget:
                problems.append(f"budget.{bk} is missing")

    return problems
