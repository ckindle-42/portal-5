"""Decision engine — tool/parameter selection layer (Gap 7).

Optional architecture: builds only if tool-selection quality becomes a bottleneck.
Ships last per the build plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCandidate:
    name: str
    score: float
    reason: str = ""


def select_tools(
    observations: dict[str, Any],
    available_tools: list[str],
    *,
    strategy: str = "coverage",
) -> list[ToolCandidate]:
    """Select the best tools for the current engagement state.

    strategy='coverage': pick tools that maximize unexplored surface.
    strategy='rapid': pick the fastest tools first.
    """
    if not observations:
        return [
            ToolCandidate(name=t, score=1.0, reason="initial coverage") for t in available_tools[:3]
        ]

    # Prioritize tools that target observed open ports/services
    scored: list[ToolCandidate] = []
    open_ports = observations.get("open_ports", [])
    if open_ports is True or (isinstance(open_ports, list) and len(open_ports) > 0):
        for t in available_tools:
            if "exploit" in t or "check" in t:
                scored.append(
                    ToolCandidate(name=t, score=0.9, reason="ports open, exploit candidate")
                )
    return (
        scored
        if scored
        else [ToolCandidate(name=t, score=0.5, reason="initial probe") for t in available_tools[:2]]
    )


def select_parameters(
    tool_name: str,
    observations: dict[str, Any],
    base_params: dict[str, Any],
) -> dict[str, Any]:
    """Select optimal parameters for a tool based on current observations."""
    params = dict(base_params)
    if "open_ports" in observations and tool_name == "run_nmap_scan":
        params["scan_type"] = "version"
    if "confirmed_cve" in observations and tool_name == "exploit_service":
        params["cve_id"] = observations.get("confirmed_cve", params.get("cve_id", ""))
    return params
