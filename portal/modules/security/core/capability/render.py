"""Human-readable views over the capability index and tool catalog (Phase 3).

Used by the CLI (`portal security capability list/query/tools/arsenal`) and
available for the decide step to embed a compact capability digest into an
LLM prompt.
"""

from __future__ import annotations

from portal.modules.security.core.capability.index import Capability
from portal.modules.security.core.capability.tool_inventory import load_tool_catalog


def render_capabilities(caps: list[Capability]) -> str:
    """One line per capability: id, phase/domain, technique, tools, oracle."""
    if not caps:
        return "(no capabilities matched)"
    lines = []
    for c in caps:
        tools = ", ".join(c.tools) if c.tools else "-"
        oracle = c.oracle or "-"
        lines.append(
            f"[{c.phase}/{c.domain}] {c.id} — {c.technique}\n"
            f"    tools: {tools} | oracle: {oracle} | source: {c.source}"
        )
    return "\n".join(lines)


def render_tool_arsenal(*, phase: str | None = None, service: str | None = None) -> str:
    """One line per declared tool, optionally filtered by phase or service."""
    tools = load_tool_catalog()
    if phase is not None:
        tools = [t for t in tools if t.get("phase") == phase]
    if service is not None:
        tools = [t for t in tools if service in (t.get("targets_services") or [])]
    if not tools:
        return "(no tools matched)"
    lines = []
    for t in tools:
        services = ", ".join(t.get("targets_services") or []) or "-"
        lines.append(
            f"{t['name']} ({t.get('category', '-')}, {t.get('phase', '-')}) "
            f"— services: {services}\n    {t.get('notes', '')}"
        )
    return "\n".join(lines)
