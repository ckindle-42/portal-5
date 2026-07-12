"""Env-var + per-workspace config resolution for the tool preselector.

Two levels of opt-in, both required for the feature to activate on a
given request:

1. Global flag ``PORTAL5_TOOL_PRESELECT`` (default off).
2. Per-workspace ``tool_preselect:`` block in ``config/portal.yaml``
   (absence -> bypassed even when the global flag is on).

See portal/platform/inference/tool_preselect/README.md for the full design.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_PRESELECT_MODEL = "hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M"


@dataclass(frozen=True)
class WorkspacePreselectConfig:
    """Resolved per-workspace preselect settings."""

    enabled: bool
    k: int
    confidence_floor: float


def global_preselect_enabled() -> bool:
    """``PORTAL5_TOOL_PRESELECT`` — global kill switch, default off."""
    return os.environ.get("PORTAL5_TOOL_PRESELECT", "0") == "1"


def preselect_model() -> str:
    """``PORTAL5_TOOL_PRESELECT_MODEL`` — Ollama tag for the preselector."""
    return os.environ.get("PORTAL5_TOOL_PRESELECT_MODEL", DEFAULT_PRESELECT_MODEL)


def default_k(total_tools: int) -> int:
    """K selection per §1.4: bypass at <=5, K=5 for 6-15, else min(8, ceil(0.4*N))."""
    import math

    if total_tools <= 5:
        return 0
    if total_tools <= 15:
        return 5
    return min(8, math.ceil(total_tools * 0.4))


def resolve_workspace_config(
    workspace_config: dict, total_tools: int
) -> WorkspacePreselectConfig | None:
    """Resolve a workspace's ``tool_preselect:`` block.

    Returns None if the workspace hasn't opted in (no ``tool_preselect:``
    key, or ``enabled: false``) — the caller must bypass in that case.
    """
    block = workspace_config.get("tool_preselect")
    if not block or not block.get("enabled", False):
        return None
    k = block.get("k", default_k(total_tools))
    confidence_floor = block.get("confidence_floor", 0.5)
    return WorkspacePreselectConfig(enabled=True, k=k, confidence_floor=confidence_floor)


def is_preselect_enabled(workspace_id: str, workspace_config: dict) -> bool:
    """True only when both the global flag AND the workspace opt-in are set,
    AND the workspace hasn't been runtime auto-disabled (§5.2)."""
    if not global_preselect_enabled():
        return False
    tools = workspace_config.get("tools", [])
    resolved = resolve_workspace_config(workspace_config, len(tools))
    if resolved is None:
        return False

    from portal.platform.inference.tool_preselect.state import is_auto_disabled

    return not is_auto_disabled(workspace_id)
