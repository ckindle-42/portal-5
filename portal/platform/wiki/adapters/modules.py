"""Module toggle resolver.

Enabled state is `config/portal.yaml` `modules.<name>.enabled`. Wiki
`unit-module-*` units document the switch; they do not hold it. Workspace
and fleet membership still come from each entry's `module:` tag.
"""

from __future__ import annotations

from typing import Any

DEFAULT_ENABLED_MODULES: frozenset[str] = frozenset(
    {
        "security",
        "general",
        "coding",
        "media",
        "cad",
        "documents",
        "research",
        "compliance",
        "image",
        "vulnintel",
        "icsot",
        "detection",
        "data",
        "netforensics",
    }
)
# Bench apparatus, video, and music are off unless config (or, for eval, the env) says on.
# security_redteam carries the offensive-generation security variants only
# (redteam / redteam-deep / purpleteam-exec); it is enabled for a lab
# generation run, not for everyday traffic.
DEFAULT_DISABLED_MODULES: frozenset[str] = frozenset({"eval", "music", "security_redteam", "video"})

ALL_MODULES: frozenset[str] = DEFAULT_ENABLED_MODULES | DEFAULT_DISABLED_MODULES


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


def _config_enabled_state(module: str) -> bool | None:
    """Return `modules.<name>.enabled` from portal.yaml, or None if unset."""
    from portal.platform.inference.config import load_portal_config

    spec = load_portal_config().modules.get(module)
    if spec is None:
        return None
    return spec.enabled


def _enabled_from(cfg: Any) -> set[str]:
    """Enabled module names on one config, including the eval env opt-in."""
    enabled: set[str] = set()
    for mod in ALL_MODULES:
        if mod == "eval" and _eval_env_opt_in():
            enabled.add(mod)
            continue
        spec = cfg.modules.get(mod)
        state = spec.enabled if spec is not None else mod in DEFAULT_ENABLED_MODULES
        if state:
            enabled.add(mod)
    return enabled


def enabled_modules() -> list[str]:
    """Modules whose config switch is on, else the documented default."""
    from portal.platform.inference.config import load_portal_config

    return sorted(_enabled_from(load_portal_config()))


def _active(config: Any, mods: list[str] | None) -> set[str]:
    return set(mods) if mods is not None else _enabled_from(config)


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


def is_workspace_disabled(
    workspace_id: str, mods: list[str] | None = None, config: Any = None
) -> bool:
    """True if the workspace, or ``engine::variant``, belongs to a disabled module."""
    from portal.platform.inference.config import load_portal_config, variant_module

    cfg = load_portal_config() if config is None else config
    enabled = _active(cfg, mods)
    base, _sep, variant = workspace_id.partition("::")
    spec = cfg.workspaces.get(base)
    if spec is None:
        return False
    if spec.module not in enabled:
        return True
    if not variant or variant not in spec.variants:
        return False
    return variant_module(spec.module, spec.variants[variant]) not in enabled


def served_ids(config: Any, mods: list[str] | None = None) -> set[str]:
    """Workspace ids plus ``engine::variant`` ids whose module is enabled."""
    from portal.platform.inference.config import variant_module

    enabled = _active(config, mods)
    ids: set[str] = set()
    for ws_id, spec in config.workspaces.items():
        if spec.module not in enabled:
            continue
        ids.add(ws_id)
        for name, variant in spec.variants.items():
            if variant_module(spec.module, variant) in enabled:
                ids.add(f"{ws_id}::{name}")
    return ids


def router_labels(config: Any, mods: list[str] | None = None) -> set[str]:
    """Ids the router may offer: served engines and variants, without bench lanes."""
    return {
        wid for wid in served_ids(config, mods) if not wid.split("::", 1)[0].startswith("bench-")
    }


def preset_ids(config: Any, mods: list[str] | None = None) -> set[str]:
    """Open WebUI preset ids: exposed engines only. Variants are never user-facing (R7)."""
    enabled = _active(config, mods)
    return {
        ws_id
        for ws_id, spec in config.workspaces.items()
        if spec.module != "eval" and spec.expose_to_owui and spec.module in enabled
    }
