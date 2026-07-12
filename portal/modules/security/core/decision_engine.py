"""Decision engine — tool/parameter selection.

Promoted to portal.platform.agent.rank (TASK_AGENT_LOOP_PLATFORM_V1). Re-exported
here for back-compat: existing security imports and bench_integration keep working.
"""

from __future__ import annotations

from portal.platform.agent.rank import (
    ToolCandidate,
    select_parameters,
    select_tools,
)

__all__ = ["ToolCandidate", "select_tools", "select_parameters"]
