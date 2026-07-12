"""Tests that sync-config is idempotent and generated artifacts match portal.yaml.

Verifies the CI guard: running sync-config twice should produce no diff in
workspace_routing (backends.yaml), .mcp.json, or imports/openwebui/workspaces/.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent


def _run_sync_config() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "portal.platform.inference.sync_config"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    if result.returncode != 0:
        raise RuntimeError(f"sync-config failed:\n{result.stderr}")
    return result.stdout


def test_sync_config_runs_without_error() -> None:
    """sync-config must exit 0 with the current portal.yaml."""
    output = _run_sync_config()
    assert "sync-config: done" in output


def test_sync_config_is_idempotent() -> None:
    """Running sync-config twice must produce 'no change' on the second run."""
    _run_sync_config()  # first run — may update
    output = _run_sync_config()  # second run — must be no-op
    assert "no change" in output or "0 created, 0 updated, 0 removed" in output, (
        f"sync-config was not idempotent:\n{output}"
    )


def test_backends_yaml_workspace_routing_matches_catalog() -> None:
    """Every workspace in portal.yaml must appear in backends.yaml workspace_routing."""
    portal_yaml_path = REPO / "config" / "portal.yaml"
    backends_path = REPO / "config" / "backends.yaml"

    portal_raw = yaml.safe_load(portal_yaml_path.read_text()) or {}
    backends_raw = yaml.safe_load(backends_path.read_text()) or {}

    portal_ws = set(portal_raw.get("workspaces", {}).keys())
    backends_routing = set(backends_raw.get("workspace_routing", {}).keys())

    missing = portal_ws - backends_routing
    extra = backends_routing - portal_ws

    assert not missing, (
        f"Workspaces in portal.yaml but missing from workspace_routing: {sorted(missing)}"
    )
    assert not extra, f"workspace_routing entries with no workspace in portal.yaml: {sorted(extra)}"


def test_mcp_json_matches_fleet() -> None:
    """.mcp.json IDE entries must match ide-exposed servers in portal.yaml fleet."""
    portal_yaml_path = REPO / "config" / "portal.yaml"
    mcp_json_path = REPO / ".mcp.json"

    portal_raw = yaml.safe_load(portal_yaml_path.read_text()) or {}
    mcp_raw = json.loads(mcp_json_path.read_text())

    fleet = portal_raw.get("mcp_fleet", [])
    ide_names = {s["name"] for s in fleet if s.get("expose_to_ide", True)}
    mcp_names = set(mcp_raw.get("mcpServers", {}).keys())

    assert ide_names == mcp_names, (
        f"IDE-exposed fleet names ≠ .mcp.json keys\n"
        f"  Only in fleet: {sorted(ide_names - mcp_names)}\n"
        f"  Only in .mcp.json: {sorted(mcp_names - ide_names)}"
    )


def test_owui_presets_cover_all_exposed_workspaces() -> None:
    """Every expose_to_owui=true workspace in an enabled module must have a
    workspace_*.json preset file (Gate 1: disabled-module workspaces are
    correctly excluded, same as any other expose_to_owui=False workspace —
    see sync_config.emit_owui_presets)."""
    from portal.platform.wiki.adapters.modules import owui_workspaces

    portal_yaml_path = REPO / "config" / "portal.yaml"
    ws_dir = REPO / "imports" / "openwebui" / "workspaces"

    portal_raw = yaml.safe_load(portal_yaml_path.read_text()) or {}
    workspaces = portal_raw.get("workspaces", {})

    hidden_by_module = set(owui_workspaces() or ())
    exposed = {
        ws_id
        for ws_id, spec in workspaces.items()
        if spec.get("expose_to_owui", True) and ws_id not in hidden_by_module
    }
    preset_ids = {
        json.loads(f.read_text()).get("id", "") for f in sorted(ws_dir.glob("workspace_*.json"))
    }

    missing = exposed - preset_ids
    assert not missing, f"expose_to_owui=true workspaces with no preset JSON: {sorted(missing)}"


def test_no_orphan_owui_presets() -> None:
    """No workspace_*.json preset may point at a workspace not in portal.yaml."""
    portal_yaml_path = REPO / "config" / "portal.yaml"
    ws_dir = REPO / "imports" / "openwebui" / "workspaces"

    portal_raw = yaml.safe_load(portal_yaml_path.read_text()) or {}
    live_ws = set(portal_raw.get("workspaces", {}).keys())

    orphans = []
    for f in sorted(ws_dir.glob("workspace_*.json")):
        ws_id = json.loads(f.read_text()).get("id", "")
        if ws_id and ws_id not in live_ws:
            orphans.append(ws_id)

    assert not orphans, (
        f"Orphan OWUI preset files (workspace no longer in portal.yaml): {sorted(orphans)}"
    )
