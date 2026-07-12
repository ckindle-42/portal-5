"""Tool preselector — public interface (§3.3).

Phase 1: structural stub. Unconditionally falls back to the full
``effective_tools`` set with ``outcome.reason == "bypass_disabled"``.
No Ollama call, no config resolution — that logic lands in Phase 2
once both preselector-model candidates are pulled and bench-verified.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class PreselectOutcome:
    """Result metadata from one preselect() call.

    ``reason`` is one of the Prometheus outcome labels from §1.8:
    ok, fallback_timeout, fallback_lowconf, fallback_parse,
    fallback_empty, bypass_low_tools, bypass_disabled.
    """

    reason: str
    latency_ms: int


async def preselect(
    effective_tools: set[str],
    user_turn_content: str,
    workspace_id: str,
    workspace_config: dict,
) -> tuple[set[str], PreselectOutcome]:
    """Narrow ``effective_tools`` to the query-relevant subset.

    Returns (subset, outcome). ``subset`` is always a subset of
    ``effective_tools``. On any fallback path, ``subset ==
    effective_tools`` and ``outcome`` carries the fallback reason.

    Never raises. All errors caught -> fallback with outcome.
    """
    start = time.monotonic()
    latency_ms = int((time.monotonic() - start) * 1000)
    return effective_tools, PreselectOutcome(reason="bypass_disabled", latency_ms=latency_ms)
