"""Tests that MCP fleet is single-sourced in portal.yaml.

Every MCP id/port must appear exactly once. The pipeline-discovered set
must be a subset of the fleet. The IDE-advertised set must also be a subset.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.platform.inference.config import get_pipeline_mcp_servers, load_portal_config
from portal.platform.inference.tool_registry import MCP_SERVERS

REPO = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def _restore_config_cache():
    """Reload config from real portal.yaml before each fleet test.

    Other test files call load_portal_config(_force_reload=True) with minimal
    YAML fixtures, which leaves the module-level cache pointing at an empty
    fleet. This fixture resets it to the real config before each test here.
    """
    load_portal_config(_force_reload=True)
    yield
    # Restore to real config after the test too
    load_portal_config(_force_reload=True)


def test_no_duplicate_ports_in_fleet() -> None:
    """No two MCP servers in portal.yaml fleet may share a port."""
    config = load_portal_config()
    ports = [s.port for s in config.mcp_fleet if s.port is not None]
    seen: set[int] = set()
    dupes = []
    for p in ports:
        if p in seen:
            dupes.append(p)
        seen.add(p)
    assert not dupes, f"Duplicate ports in mcp_fleet: {dupes}"


def test_no_duplicate_ids_in_fleet() -> None:
    """No two MCP servers in portal.yaml fleet may share an id."""
    config = load_portal_config()
    ids = [s.id for s in config.mcp_fleet]
    seen: set[str] = set()
    dupes = []
    for i in ids:
        if i in seen:
            dupes.append(i)
        seen.add(i)
    assert not dupes, f"Duplicate ids in mcp_fleet: {dupes}"


def test_pipeline_mcp_servers_subset_of_fleet() -> None:
    """Every key in tool_registry.MCP_SERVERS must be in the portal.yaml fleet."""
    config = load_portal_config()
    fleet_ids = {s.id for s in config.mcp_fleet}
    pipeline_ids = set(MCP_SERVERS.keys())
    extra = pipeline_ids - fleet_ids
    assert not extra, f"MCP_SERVERS keys not in fleet: {sorted(extra)}"


def test_pipeline_mcp_servers_all_pipeline_exposed() -> None:
    """Every key in MCP_SERVERS must have expose_to_pipeline=True in the fleet."""
    config = load_portal_config()
    pipeline_exposed = {s.id for s in config.mcp_fleet if s.expose_to_pipeline}
    non_exposed = set(MCP_SERVERS.keys()) - pipeline_exposed
    assert not non_exposed, (
        f"MCP_SERVERS has servers not expose_to_pipeline in fleet: {non_exposed}"
    )


def test_fleet_pipeline_exposed_matches_mcp_servers() -> None:
    """get_pipeline_mcp_servers() must equal MCP_SERVERS (same derivation)."""
    config = load_portal_config()
    derived = get_pipeline_mcp_servers(config)
    # Allow env-override variation but keys must match
    assert set(derived.keys()) == set(MCP_SERVERS.keys()), (
        f"Fleet pipeline keys mismatch:\n"
        f"  derived: {sorted(derived.keys())}\n"
        f"  MCP_SERVERS: {sorted(MCP_SERVERS.keys())}"
    )


def test_ide_servers_in_fleet() -> None:
    """.mcp.json server names must all be from the fleet (expose_to_ide=True entries)."""
    mcp_json = json.loads((REPO / ".mcp.json").read_text())
    mcp_names = set(mcp_json.get("mcpServers", {}).keys())

    config = load_portal_config()
    ide_names = {s.name for s in config.mcp_fleet if s.expose_to_ide}

    extra = mcp_names - ide_names
    assert not extra, f".mcp.json has servers not in fleet (expose_to_ide=True): {sorted(extra)}"


def test_execution_alias_recorded() -> None:
    """The 'execution' server must have 'sandbox' as an alias (drift reconciliation)."""
    config = load_portal_config()
    execution = next((s for s in config.mcp_fleet if s.id == "execution"), None)
    assert execution is not None, "MCP server 'execution' (port 8914) not found in fleet"
    assert "sandbox" in execution.aliases, (
        "'sandbox' alias not recorded on execution server (needed for backward compatibility)"
    )


def test_browser_is_ide_only() -> None:
    """The 'browser' MCP (port 8923) must not be pipeline-exposed."""
    config = load_portal_config()
    browser = next((s for s in config.mcp_fleet if s.id == "browser"), None)
    if browser is not None:
        assert not browser.expose_to_pipeline, (
            "browser MCP should not be pipeline-exposed (raw browser tools are not model-callable)"
        )
