"""portal.platform.agent — discipline-agnostic agent loop (platform core).

The reusable goal/decide/rank/loop/writeback machinery promoted out of the
security module (TASK_AGENT_LOOP_PLATFORM_V1). This package is CORE: it is
always present and MUST NOT import from portal.modules.* — modules implement
its contracts (CapabilityProvider, Executor) and plug in. Enforced by
scripts/validate_system.py check "AO. agent core".
"""

from __future__ import annotations

from .decide import decide_next_action
from .goal import Goal, validate_goal
from .interfaces import Capability, CapabilityProvider, Executor
from .loop import LoopResult, run_loop
from .rank import ToolCandidate, select_parameters, select_tools

__all__ = [
    "Goal",
    "validate_goal",
    "Capability",
    "CapabilityProvider",
    "Executor",
    "decide_next_action",
    "ToolCandidate",
    "select_tools",
    "select_parameters",
    "run_loop",
    "LoopResult",
]
