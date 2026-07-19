"""Module toggle resolver — M7 of BUILD_PROGRAM_MODULARIZATION_ALL_V1
(folding in DESIGN-MODULES-V1, the July-4 toggle design, now that modules
are structural).

Lives in wiki/adapters/, not wiki/ core: launched_mcp_ids() needs the live
mcp_fleet id list from portal.platform.inference.config, which core (the
extracted, Portal-agnostic wiki engine) may never import.

Enabled/disabled state lives in each unit-module-<name> wiki unit's
fenced yaml config block (`enabled: true|false`) — the wiki is the
source of truth, same as everything else in this system. This module
reads that state and cross-references it against the module -> workspace
ids / module -> mcp_fleet ids maps (BUILD_PROGRAM_COLLAPSE_V1.md Phase 3:
derived from each entry's `module:` tag in config/portal.yaml, not
hand-maintained) to answer the three resolver questions the four gates
need.
"""

from __future__ import annotations

import re

DEFAULT_ENABLED_MODULES: frozenset[str] = frozenset(
    {"security", "general", "coding", "media", "cad", "documents", "research", "compliance"}
)
# Per DESIGN-MODULES-V1: bench/testing apparatus is off by default.
DEFAULT_DISABLED_MODULES: frozenset[str] = frozenset({"eval"})

ALL_MODULES: frozenset[str] = DEFAULT_ENABLED_MODULES | DEFAULT_DISABLED_MODULES

_ENABLED_RE = re.compile(r"^\s*enabled:\s*(true|false)\s*$", re.MULTILINE | re.IGNORECASE)


def module_workspace_ids() -> dict[str, tuple[str, ...]]:
    """module -> workspace ids, derived from each workspace's `module:` tag
    in config/portal.yaml (BUILD_PROGRAM_COLLAPSE_V1.md Phase 3)."""
    from portal.platform.inference.config import load_portal_config

    out: dict[str, list[str]] = {m: [] for m in ALL_MODULES}
    for wid, ws in load_portal_config().workspaces.items():
        out.setdefault(ws.module, []).append(wid)
    return {k: tuple(sorted(v)) for k, v in out.items()}


def module_mcp_ids() -> dict[str, tuple[str, ...]]:
    """module -> mcp_fleet ids, derived from each entry's `module:` tag in
    config/portal.yaml. "platform" entries (memory, mlx_transcribe,
    pipeline, wiki — infra no discipline owns) are kept under the
    "platform" key rather than folded into a discipline module."""
    from portal.platform.inference.config import load_portal_config

    out: dict[str, list[str]] = {m: [] for m in ALL_MODULES}
    platform: list[str] = []
    for m in load_portal_config().mcp_fleet:
        (platform if m.module == "platform" else out.setdefault(m.module, [])).append(m.id)
    return {"platform": tuple(sorted(platform)), **{k: tuple(sorted(v)) for k, v in out.items()}}


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


def _eval_env_opt_in() -> bool:
    """Bench-harness opt-in for the eval module via PORTAL_ENABLE_EVAL, mirroring
    ``portal.platform.inference.config._eval_enabled()``'s env check. Duplicated
    rather than imported — that function's own fallback path calls
    ``enabled_modules()`` here, so importing it back would be circular.

    Found live 2026-07-18 (GATE-D ablation): before this, PORTAL_ENABLE_EVAL
    only ever affected the import-time WORKSPACES snapshot (config.py's
    get_workspace_dict), never this module's per-request
    is_workspace_disabled() gate — so setting the env var made bench-*
    workspaces visible in the dict but every actual request to one still
    404'd, contradicting Rule 6's documented "doesn't require a persisted
    wiki toggle" claim. Now both gates agree.
    """
    import os

    return os.environ.get("PORTAL_ENABLE_EVAL", "").lower() in ("true", "1", "yes")


def enabled_modules() -> list[str]:
    """Every module currently enabled — wiki state if present, else the
    documented default (everything except eval). eval additionally honors
    PORTAL_ENABLE_EVAL as a transient opt-in that doesn't require flipping
    the persisted toggle (see _eval_env_opt_in)."""
    result = []
    for mod in sorted(ALL_MODULES):
        if mod == "eval" and _eval_env_opt_in():
            result.append(mod)
            continue
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
    Platform-tagged ids (memory, mlx_transcribe, pipeline, wiki) are also
    always on — they aren't owned by any single discipline module, so no
    module being disabled should ever drop them.
    """
    mods = enabled_modules() if mods is None else mods
    mcp_ids = module_mcp_ids()

    ids: set[str] = set(mcp_ids.get("general", ())) | set(mcp_ids.get("platform", ()))
    for mod in mods:
        ids.update(mcp_ids.get(mod, ()))
    return sorted(ids)


def owui_workspaces(mods: list[str] | None = None) -> list[str] | None:
    """Workspace ids that should be OWUI-exposed, given the enabled module
    set. Returns None to mean "no restriction" when every module is enabled
    (the common case) — callers should treat None as "don't filter" rather
    than "expose nothing"."""
    mods = enabled_modules() if mods is None else mods
    disabled = ALL_MODULES - set(mods)
    if not disabled:
        return None
    ws_ids = module_workspace_ids()
    hidden: set[str] = set()
    for mod in disabled:
        hidden.update(ws_ids.get(mod, ()))
    return sorted(hidden)  # caller subtracts this from the full workspace set


def is_workspace_disabled(workspace_id: str, mods: list[str] | None = None) -> bool:
    """True if workspace_id belongs to a currently-disabled module."""
    mods = enabled_modules() if mods is None else mods
    disabled = ALL_MODULES - set(mods)
    ws_ids = module_workspace_ids()
    return any(workspace_id in ws_ids.get(mod, ()) for mod in disabled)
