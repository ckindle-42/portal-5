"""The compliance module's workspace config surface — same pattern as
portal.modules.general.config: a name-based pointer into config/portal.yaml
(the single source of truth), not a duplicate store.
"""

COMPLIANCE_WORKSPACE_IDS: tuple[str, ...] = ("auto-compliance",)


def compliance_workspaces() -> dict[str, dict]:
    """The compliance module's workspace entries, straight from portal.yaml."""
    from portal.platform.storage import load_portal_config

    cfg = load_portal_config()
    return {wid: cfg.workspaces[wid].model_dump() for wid in COMPLIANCE_WORKSPACE_IDS}
