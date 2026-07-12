"""The general module's workspace config surface.

Workspaces belonging to this discipline (config/portal.yaml, verified by
name, not a dedicated field — portal.yaml has no per-workspace "module"
tag yet, so this is a name-based pointer to the real config, not a
duplicate of it):
"""

GENERAL_WORKSPACE_IDS: tuple[str, ...] = ("auto-daily", "auto-general-uncensored")


def general_workspaces() -> dict[str, dict]:
    """The general module's workspace entries, straight from portal.yaml —
    no separate config store, this reads the single source of truth."""
    from portal.platform.storage import load_portal_config

    cfg = load_portal_config()
    return {wid: cfg.workspaces[wid].model_dump() for wid in GENERAL_WORKSPACE_IDS}
