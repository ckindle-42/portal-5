"""Config-family checks: portal.yaml load + Rule 6 single-source-of-truth."""

from __future__ import annotations

from ._shared import REPO_ROOT
from .registry import register


@register("config_loads", "C. config round-trip", order=2)
def check_config_loads() -> tuple[str, str, list[dict]]:
    """C. portal.yaml loads via PortalConfig."""
    from portal.platform.inference.config import load_portal_config

    cfg = load_portal_config()
    n_ws = len(cfg.workspaces)
    n_mcp = len(cfg.mcp_fleet)
    n_models = len(cfg.models)
    if n_ws == 0:
        return "FAIL", "PortalConfig.workspaces is empty", []
    if n_mcp == 0:
        return "WARN", "PortalConfig.mcp_fleet is empty (unusual)", []
    return "PASS", f"{n_ws} workspaces · {n_mcp} MCP · {n_models} models", []


@register("rule_6", "D. Rule 6 cross-check", order=3)
def check_rule_6() -> tuple[str, str, list[dict]]:
    """D. portal.yaml workspaces ↔ backends.yaml workspace_routing ↔ WORKSPACES.

    module: eval workspaces (bench-*) are gated off WORKSPACES by default
    (BUILD_PROGRAM_COLLAPSE_V1.md Phase 4), so ws_router is compared against
    portal.yaml's non-eval-gated subset. workspace_routing is different: it's
    a static backend-group lookup table for every known workspace, NOT gated
    on module-enabled state (see sync_config.emit_workspace_routing's
    docstring — gating it on live enable state made its completeness depend
    on whatever env var happened to be set in whichever shell last ran
    sync-config, found live 2026-07-18), so ws_backends is compared against
    the full set instead.
    """
    import yaml

    from portal.platform.inference.config import _eval_enabled, load_portal_config
    from portal.platform.inference.router.workspaces import WORKSPACES

    cfg = load_portal_config()
    eval_on = _eval_enabled()
    ws_all = set(cfg.workspaces.keys())
    ws_yaml = {wid for wid, spec in cfg.workspaces.items() if eval_on or spec.module != "eval"}
    ws_router = set(WORKSPACES.keys())

    backends_path = REPO_ROOT / "config" / "backends.yaml"
    backends = yaml.safe_load(backends_path.read_text())
    ws_backends = set(backends.get("workspace_routing", {}).keys())

    if ws_yaml != ws_router or ws_all != ws_backends:
        details = []
        if ws_yaml - ws_router:
            details.append(f"yaml extra: {ws_yaml - ws_router}")
        if ws_router - ws_yaml:
            details.append(f"router extra: {ws_router - ws_yaml}")
        if ws_all - ws_backends:
            details.append(f"backends missing: {ws_all - ws_backends}")
        if ws_backends - ws_all:
            details.append(f"backends extra: {ws_backends - ws_all}")
        return "FAIL", "; ".join(details), []
    return (
        "PASS",
        f"WORKSPACES agrees with portal.yaml ({len(ws_yaml)}); workspace_routing covers all {len(ws_all)}",
        [],
    )
