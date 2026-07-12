"""Runtime self-healing state for the tool preselector (§5.2).

Per-workspace ring buffer of the last 100 preselect outcomes. When the
miss rate (primary model requested a tool that was filtered out)
exceeds 5% over that window, the workspace is auto-disabled in
process memory — NOT written to config/portal.yaml. A Portal restart
resets the flag; the durable fix (removing the workspace's opt-in) is
an operator decision made after reviewing the
``portal5_toolpreselect_auto_disabled_total`` metric.

Process-lifetime, module-level state — same pattern as the workspace
semaphores in router/concurrency.py (in-memory, not persisted).
"""

from __future__ import annotations

import logging
import threading
from collections import deque

logger = logging.getLogger(__name__)

_WINDOW_SIZE = 100
_MISS_RATE_THRESHOLD = 0.05

_lock = threading.Lock()
_outcome_windows: dict[str, deque[bool]] = {}  # workspace_id -> deque of "was_miss"
_auto_disabled: set[str] = set()


def record_outcome(workspace_id: str, was_miss: bool) -> None:
    """Record one preselect-dispatch outcome (miss or hit) for a workspace.

    Called from the dispatch layer when a primary-model tool call is
    checked against the preselected set — NOT from preselect() itself
    (a fallback outcome from preselect() is not a miss; a miss only
    happens when preselection actually narrowed the set and the model
    asked for something outside it).
    """
    with _lock:
        window = _outcome_windows.setdefault(workspace_id, deque(maxlen=_WINDOW_SIZE))
        window.append(was_miss)
        if len(window) >= _WINDOW_SIZE:
            miss_rate = sum(window) / len(window)
            if miss_rate > _MISS_RATE_THRESHOLD and workspace_id not in _auto_disabled:
                _auto_disabled.add(workspace_id)
                logger.info(
                    "tool_preselect auto-disabled ws=%s miss_rate=%.3f "
                    "window=%d last_100_misses=%d",
                    workspace_id,
                    miss_rate,
                    len(window),
                    sum(window),
                )
                from portal.platform.inference.tool_preselect.metrics import (
                    record_auto_disabled,
                )

                record_auto_disabled(workspace_id)


def is_auto_disabled(workspace_id: str) -> bool:
    with _lock:
        return workspace_id in _auto_disabled


def reset(workspace_id: str | None = None) -> None:
    """Test/ops helper — clear auto-disable state. None clears everything."""
    with _lock:
        if workspace_id is None:
            _outcome_windows.clear()
            _auto_disabled.clear()
        else:
            _outcome_windows.pop(workspace_id, None)
            _auto_disabled.discard(workspace_id)
