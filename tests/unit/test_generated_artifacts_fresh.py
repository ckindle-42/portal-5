"""Tests that sync-config is idempotent and generated artifacts match portal.yaml.

Verifies the CI guard: running sync-config twice should produce no diff in
workspace_routing (backends.yaml), .mcp.json, or imports/openwebui/workspaces/.
"""

from __future__ import annotations

import json
import os
import shutil
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
        env={**os.environ, "PORTAL_SYNC_SKIP_PIPELINE_CHECK": "1"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"sync-config failed:\n{result.stderr}")
    return result.stdout


def _write_scratch_sync_tree(root: Path) -> None:
    shutil.copytree(REPO / "config", root / "config")
    shutil.copy2(REPO / ".mcp.json", root / ".mcp.json")
    shutil.copy2(REPO / "opencode.jsonc", root / "opencode.jsonc")
    shutil.copytree(
        REPO / "imports" / "openwebui" / "workspaces",
        root / "imports" / "openwebui" / "workspaces",
    )
    (root / "docs").mkdir()
    (root / "portal_wiki" / "canonical").mkdir(parents=True)
    (root / "docs" / "ADMIN_GUIDE.md").write_text(
        "<!-- WIKI:GENERATED unit=unit-fact-workspace-roster -->\nstale\n"
        "<!-- /WIKI:GENERATED -->\n",
        encoding="utf-8",
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


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


def test_model_swap_sync_writes_only_runtime_artifacts(tmp_path, monkeypatch):
    from portal.platform.inference import config as config_module
    from portal.platform.inference import sync_config
    from portal.platform.wiki import store
    from portal.platform.wiki.adapters import modules, seed_facts

    _write_scratch_sync_tree(tmp_path)
    portal_yaml = tmp_path / "config" / "portal.yaml"
    portal_cfg = yaml.safe_load(portal_yaml.read_text())
    workspace = next(name for name in portal_cfg["workspaces"] if name.startswith("auto-"))
    old_hint = portal_cfg["workspaces"][workspace]["model_hint"]
    portal_cfg["workspaces"][workspace]["model_hint"] = "model-swap-test"
    portal_yaml.write_text(yaml.safe_dump(portal_cfg), encoding="utf-8")
    monkeypatch.setattr(sync_config, "REPO", tmp_path)
    monkeypatch.setattr(config_module, "PORTAL_YAML", portal_yaml)
    monkeypatch.setattr(config_module, "_CONFIG_CACHE", {})
    monkeypatch.setattr(seed_facts, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(modules, "launched_mcp_ids", lambda _mods=None: [])
    monkeypatch.setattr(modules, "enabled_modules", lambda: ["general"])
    monkeypatch.setattr(modules, "owui_workspaces", lambda _mods=None: [])
    monkeypatch.setenv("PORTAL_SYNC_SKIP_PIPELINE_CHECK", "1")
    monkeypatch.chdir(tmp_path)
    assert portal_cfg["workspaces"][workspace]["model_hint"] != old_hint
    store.set_canonical_dir(tmp_path / "portal_wiki" / "canonical")
    before = _snapshot(tmp_path)
    try:
        assert sync_config.main() == 0
    finally:
        store.reset_canonical_dir()

    after = _snapshot(tmp_path)
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    allowed = {
        "config/backends.yaml",
        ".mcp.json",
        "config/modules.generated.yaml",
    }
    unexpected = {
        path
        for path in changed
        if path not in allowed and not path.startswith("imports/openwebui/workspaces/")
    }
    assert not unexpected, f"sync-config changed non-runtime paths: {sorted(unexpected)}"


def test_backends_yaml_workspace_routing_matches_catalog() -> None:
    """Every workspace in portal.yaml must appear in backends.yaml
    workspace_routing — a static backend-group lookup table, NOT gated on
    module-enabled state (unlike Gate 1/OWUI presets and Gate 2/.mcp.json;
    see sync_config.emit_workspace_routing's docstring). Gating this table
    on live enable state made its completeness depend on whatever env var/
    toggle state happened to be active in whichever shell last ran
    sync-config — found live 2026-07-18 chasing a GATE-D ablation hint-
    validation bug that looked like stale models but wasn't."""
    portal_yaml_path = REPO / "config" / "portal.yaml"
    backends_path = REPO / "config" / "backends.yaml"

    portal_raw = yaml.safe_load(portal_yaml_path.read_text()) or {}
    # Full catalog: bench lanes moved to config/bench_workspaces.yaml (C step 1)
    # but stay in the routing table, env-independently.
    from portal.platform.inference.config import load_bench_workspaces_raw

    portal_ws = {
        *(portal_raw.get("workspaces", {}).keys()),
        *load_bench_workspaces_raw(REPO).keys(),
    }
    backends_raw = yaml.safe_load(backends_path.read_text()) or {}

    backends_routing = set(backends_raw.get("workspace_routing", {}).keys())

    missing = portal_ws - backends_routing
    extra = backends_routing - portal_ws

    assert not missing, (
        f"Workspaces in portal.yaml but missing from workspace_routing: {sorted(missing)}"
    )
    assert not extra, f"workspace_routing entries with no workspace in portal.yaml: {sorted(extra)}"


def test_mcp_json_matches_fleet() -> None:
    """.mcp.json IDE entries must match launched, ide-exposed fleet servers."""
    portal_yaml_path = REPO / "config" / "portal.yaml"
    mcp_json_path = REPO / ".mcp.json"

    portal_raw = yaml.safe_load(portal_yaml_path.read_text()) or {}
    mcp_raw = json.loads(mcp_json_path.read_text())

    from portal.platform.wiki.adapters.modules import launched_mcp_ids

    fleet = portal_raw.get("mcp_fleet", [])
    launched = set(launched_mcp_ids())
    ide_names = {
        s["name"] for s in fleet if s.get("expose_to_ide", True) and s.get("id") in launched
    }
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
