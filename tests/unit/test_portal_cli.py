"""Smoke tests for the portal CLI skeleton (M5 Stage 2).

Verifies:
- portal --help exits 0 and mentions the 'config' command group.
- portal config show exits 0 and emits valid JSON with expected keys.
- portal config show output reflects the production portal.yaml values.
"""

from __future__ import annotations

import json
import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "portal_pipeline.cli", *args],
        capture_output=True,
        text=True,
    )


def test_portal_help() -> None:
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert "config" in result.stdout


def test_portal_config_show_exits_0() -> None:
    result = _run("config", "show")
    assert result.returncode == 0, result.stderr


def test_portal_config_show_valid_json() -> None:
    result = _run("config", "show")
    data = json.loads(result.stdout)
    assert "ollama_url" in data
    assert "workspaces" in data
    assert "workspace_count" in data
    assert "mcp_fleet_count" in data


def test_portal_config_show_workspace_count() -> None:
    result = _run("config", "show")
    data = json.loads(result.stdout)
    assert data["workspace_count"] > 0
    assert len(data["workspaces"]) == data["workspace_count"]


def test_portal_config_show_mcp_fleet() -> None:
    result = _run("config", "show")
    data = json.loads(result.stdout)
    assert data["mcp_fleet_count"] > 0
    for entry in data["mcp_fleet"]:
        assert "id" in entry
        assert "name" in entry
