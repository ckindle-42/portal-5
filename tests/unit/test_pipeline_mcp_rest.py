"""Pipeline-MCP REST contract tests.

Guards the in-pipeline coding-tool path (Path B): the portal_pipeline
ToolRegistry discovers tools via GET /tools and dispatches via
POST /tools/{name}. If pipeline_mcp.py drops a REST route or the manifest
drifts from the @mcp.tool() set, the auto-coding-agentic workspace silently
loses explore_repository. This test fails loudly on that regression.

The parity check is static (source regex) so it runs without the vendored
`mcp` dependency. The live-route check is gated on `mcp` being importable.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

_SRC_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "portal"
    / "platform"
    / "mcp_host"
    / "pipeline_mcp.py"
)
_SRC = _SRC_PATH.read_text()

_DATA_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "config"
    / "inference"
    / "pipeline_mcp_tools_manifest.json"
)

EXPECTED_TOOLS = {
    "get_pipeline_status",
    "list_workspaces",
    "get_loaded_models",
    "get_metrics_summary",
    "get_workspace_recommendation",
    "explore_repository",
    "trigger_backend_warmup",
    "read_text_file",
    "list_directory",
    "search_files",
    "write_file",
}


def _manifest_names() -> set[str]:
    # C2 of TASK_PORTAL_SIMPLIFY_V1 extracted the inline TOOLS_MANIFEST
    # literal to config/inference/pipeline_mcp_tools_manifest.json; the
    # parity guard now reads the data file instead of the source text.
    import json

    return {t["name"] for t in json.loads(_DATA_PATH.read_text())}


def _tool_names() -> set[str]:
    return set(re.findall(r"@mcp\.tool\(\)\s*\nasync def (\w+)\(", _SRC))


def _post_route_names() -> set[str]:
    return set(re.findall(r'@mcp\.custom_route\("/tools/(\w+)", methods=\["POST"\]\)', _SRC))


def test_manifest_matches_expected_tools():
    assert _manifest_names() == EXPECTED_TOOLS


def test_tool_decorators_match_expected():
    assert _tool_names() == EXPECTED_TOOLS


def test_post_routes_match_expected():
    assert _post_route_names() == EXPECTED_TOOLS


def test_three_sets_are_consistent():
    assert _manifest_names() == _tool_names() == _post_route_names()


def test_get_tools_manifest_route_present():
    assert '@mcp.custom_route("/tools", methods=["GET"])' in _SRC


def test_registered_in_pipeline_mcp_servers():
    from portal.platform.inference.tool_registry import MCP_SERVERS

    assert "pipeline" in MCP_SERVERS
    assert "8928" in MCP_SERVERS["pipeline"]


@pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason="vendored mcp dep not installed on this host",
)
def test_live_get_tools_returns_manifest():
    from starlette.testclient import TestClient

    from portal.platform.mcp_host import pipeline_mcp

    app = pipeline_mcp.mcp.streamable_http_app()
    client = TestClient(app)
    r = client.get("/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    assert names == EXPECTED_TOOLS
