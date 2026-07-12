"""Module toggle resolver — M7 of BUILD_PROGRAM_MODULARIZATION_ALL_V1
(folding in DESIGN-MODULES-V1, the July-4 toggle design, now that modules
are structural).

Lives in wiki/adapters/, not wiki/ core: launched_mcp_ids() needs the live
mcp_fleet id list from portal.platform.inference.config, which core (the
extracted, Portal-agnostic wiki engine) may never import.

Enabled/disabled state lives in each unit-module-<name> wiki unit's
fenced yaml config block (`enabled: true|false`) — the wiki is the
source of truth, same as everything else in this system. This module
reads that state and cross-references it against the two static maps
below (module -> workspace ids, module -> mcp_fleet ids) to answer the
three resolver questions the four gates need.

The static maps exist because config/portal.yaml has no per-workspace or
per-mcp-fleet-entry "module" tag yet (a real gap, not fabricated data —
verified during M1-M6). Adding that tagging is future work; until then,
this is the single place that encodes the module boundary, derived from
the M0-M6 relocation work itself.
"""

from __future__ import annotations

import re

DEFAULT_ENABLED_MODULES: frozenset[str] = frozenset(
    {"security", "general", "coding", "media", "cad", "documents", "research", "compliance"}
)
# Per DESIGN-MODULES-V1: bench/testing apparatus is off by default.
DEFAULT_DISABLED_MODULES: frozenset[str] = frozenset({"eval"})

ALL_MODULES: frozenset[str] = DEFAULT_ENABLED_MODULES | DEFAULT_DISABLED_MODULES

# module -> workspace ids (config/portal.yaml `workspaces:`), verified during M1-M6.
MODULE_WORKSPACE_IDS: dict[str, tuple[str, ...]] = {
    "general": ("auto-daily", "auto-general-uncensored"),
    "coding": (
        "auto-agentic",
        "auto-agentic-lite",
        "auto-agentic-ornith",
        "auto-coding",
        "auto-coding-agentic",
        "auto-coding-northmini",
        "auto-coding-uncensored",
        "auto-coding-uncensored-agentic",
        "auto-devstral",
    ),
    "media": ("auto-audio", "auto-creative", "auto-music"),
    "cad": ("auto-cad",),
    "documents": ("auto-documents", "auto-extract-uncensored"),
    "research": ("auto-research", "auto-data"),
    "compliance": ("auto-compliance",),
    # security and eval intentionally omitted: security's workspace set is
    # large and RBP-internal (auto-*sec*/pentest/redteam/blueteam/purpleteam
    # naming, not a fixed list worth hand-duplicating here); eval has none.
}

# module -> mcp_fleet ids (config/portal.yaml `mcp_fleet:`), verified during M0-M6.
MODULE_MCP_IDS: dict[str, tuple[str, ...]] = {
    "security": ("security", "mitre", "detections", "proxmox"),
    "general": ("filesystem", "fetch", "git", "docker"),
    "coding": ("execution",),
    "media": ("comfyui", "video", "music", "tts", "whisper"),
    "cad": ("cad_render",),
    "documents": ("documents",),
    "research": ("research", "rag", "reranker", "browser"),
    # compliance and eval: no dedicated mcp_fleet entries.
}

# mcp_fleet ids with no module mapping above (memory, mlx_transcribe, pipeline,
# wiki — verified against config/portal.yaml's mcp_fleet list) are platform-level
# infra, not owned by any single discipline module. launched_mcp_ids() must
# always include them regardless of which modules are enabled/disabled —
# otherwise Gate 2 (.mcp.json filtering) would silently drop them.
_MODULE_MAPPED_MCP_IDS: frozenset[str] = frozenset(
    id_ for ids in MODULE_MCP_IDS.values() for id_ in ids
)

_ENABLED_RE = re.compile(r"^\s*enabled:\s*(true|false)\s*$", re.MULTILINE | re.IGNORECASE)


def _unit_enabled_state(module: str) -> bool | None:
    """Read the `enabled:` field from unit-module-<module>'s fenced yaml
    config block. Returns None if the unit doesn't exist or has no
    explicit field (caller falls back to the DEFAULT_*_MODULES sets)."""
    from portal.platform.wiki.store import load_unit

    unit = load_unit(f"unit-module-{module}")
    if unit is None:
        return None
    m = _ENABLED_RE.search(unit.body)
    if m is None:
        return None
    return m.group(1).lower() == "true"


def enabled_modules() -> list[str]:
    """Every module currently enabled — wiki state if present, else the
    documented default (everything except eval)."""
    result = []
    for mod in sorted(ALL_MODULES):
        state = _unit_enabled_state(mod)
        if state is None:
            state = mod in DEFAULT_ENABLED_MODULES
        if state:
            result.append(mod)
    return result


def launched_mcp_ids(mods: list[str] | None = None) -> list[str]:
    """MCP fleet ids that should launch, given the enabled module set.

    general's base tools (filesystem/fetch/git/docker) are always on
    regardless of `mods`, per the spec's "general's base tools always on".
    Platform-level ids with no module mapping (memory, mlx_transcribe,
    pipeline, wiki) are also always on — they aren't owned by any single
    discipline module, so no module being disabled should ever drop them.
    """
    from portal.platform.inference.config import load_portal_config

    mods = enabled_modules() if mods is None else mods
    all_ids = {s.id for s in load_portal_config().mcp_fleet}
    platform_ids = all_ids - _MODULE_MAPPED_MCP_IDS

    ids: set[str] = set(MODULE_MCP_IDS.get("general", ())) | platform_ids
    for mod in mods:
        ids.update(MODULE_MCP_IDS.get(mod, ()))
    return sorted(ids)


def owui_workspaces(mods: list[str] | None = None) -> list[str] | None:
    """Workspace ids that should be OWUI-exposed, given the enabled module
    set. Returns None to mean "no restriction" when every mapped module is
    enabled (the common case) — callers should treat None as "don't filter"
    rather than "expose nothing", since unmapped workspaces (security, and
    anything not yet assigned a module) are never in this list and must not
    be silently hidden."""
    mods = enabled_modules() if mods is None else mods
    disabled = ALL_MODULES - set(mods)
    if not disabled:
        return None
    hidden: set[str] = set()
    for mod in disabled:
        hidden.update(MODULE_WORKSPACE_IDS.get(mod, ()))
    return sorted(hidden)  # caller subtracts this from the full workspace set


def is_workspace_disabled(workspace_id: str, mods: list[str] | None = None) -> bool:
    """True if workspace_id belongs to a currently-disabled module.
    Workspaces with no module mapping (security, unmapped) are never
    considered disabled by this function."""
    mods = enabled_modules() if mods is None else mods
    disabled = ALL_MODULES - set(mods)
    return any(workspace_id in MODULE_WORKSPACE_IDS.get(mod, ()) for mod in disabled)
