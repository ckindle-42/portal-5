"""EngagementGoal — the bounded, open-ended alternative to a playbook path
(TASK_SEC_GOAL_DECIDE_V1, Stage 2 Phase 1).

Same bounds a playbook must have (scope, budget, stop) — open-ended does not
mean unbounded — but no phase graph. `role` selects which capability slice
a decide step draws from: red = exploitation/recon, blue = detection/analysis,
purple = both (red acts, blue observes).
"""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_ROLES = ("red", "blue", "purple")


@dataclass
class EngagementGoal:
    intent: str
    role: str
    targets: list[str] = field(default_factory=list)
    scope: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    stop_when: list[dict] | None = None
    domain_hint: str | None = None


def validate_goal(goal: EngagementGoal) -> list[str]:
    """Mirror playbooks.validate_playbook: reject a goal with no scope or no
    budget. Nothing runs open-ended without bounds."""
    problems: list[str] = []

    if goal.role not in VALID_ROLES:
        problems.append(f"invalid role: {goal.role!r} (must be one of {VALID_ROLES})")

    if not goal.scope or not goal.scope.get("targets"):
        problems.append("scope.targets is empty or missing")

    if not goal.budget:
        problems.append("missing budget")
    else:
        for bk in ("max_iterations", "max_wall_clock_sec", "max_lab_actions"):
            if bk not in goal.budget:
                problems.append(f"budget.{bk} is missing")

    return problems
