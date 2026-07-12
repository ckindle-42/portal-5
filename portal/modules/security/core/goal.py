"""EngagementGoal — security's bounded goal, now a thin specialization of the
platform Goal (TASK_AGENT_LOOP_PLATFORM_V1). Adds `role` (red/blue/purple) and
`targets`; bound-checking is delegated to the platform, role-checked here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from portal.platform.agent.goal import Goal
from portal.platform.agent.goal import validate_goal as _platform_validate_goal

VALID_ROLES = ("red", "blue", "purple")


@dataclass
class EngagementGoal(Goal):
    role: str = "purple"
    targets: list[str] = field(default_factory=list)


def validate_goal(goal: EngagementGoal) -> list[str]:
    """Mirror playbooks.validate_playbook: role + scope + budget bounds.

    Role is checked first (security-specific), then the platform scope/budget
    bounds — preserving the historical problem ordering.
    """
    problems: list[str] = []
    if getattr(goal, "role", None) not in VALID_ROLES:
        problems.append(f"invalid role: {goal.role!r} (must be one of {VALID_ROLES})")
    problems.extend(_platform_validate_goal(goal))
    return problems
