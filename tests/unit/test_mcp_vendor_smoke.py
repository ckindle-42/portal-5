"""Smoke test for the MCPServer import path after de-vendoring (M4).

All MCP servers import MCPServer from the upstream v2 SDK. This test verifies:
- MCPServer is importable from the canonical upstream location.
- A server can be instantiated, a tool registered, and the tool listed.
- The server exposes an HTTP app factory (needed for streamable-http transport).
- No reference to the deleted portal_mcp.mcp_server vendored path survives.
"""

from __future__ import annotations

import inspect


def test_mcpserver_import_from_upstream() -> None:
    """MCPServer must come from upstream mcp.server, not the deleted vendor tree."""
    from mcp.server import MCPServer

    assert MCPServer is not None
    mod = inspect.getmodule(MCPServer)
    assert mod is not None
    assert "portal_mcp.mcp_server" not in (mod.__name__ or ""), (
        f"MCPServer is still coming from the vendored path: {mod.__name__}"
    )
    assert "mcp" in (mod.__file__ or ""), f"Unexpected MCPServer module file: {mod.__file__}"


def test_mcpserver_tool_registration() -> None:
    """Instantiate MCPServer, register a trivial tool, assert it appears in the tool list."""
    from mcp.server import MCPServer

    server = MCPServer(name="smoke-test")

    @server.tool()
    def echo(message: str) -> str:
        """Echo the input."""
        return message

    tools = server._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    assert "echo" in tool_names, f"Registered tool not found; got: {tool_names}"


def test_mcpserver_http_app_factory() -> None:
    """MCPServer instance must expose a streamable-http ASGI app."""
    from mcp.server import MCPServer

    server = MCPServer(name="smoke-http")
    app = server.streamable_http_app()
    assert app is not None, "streamable_http_app() returned None"


def test_no_vendored_portal_mcp_server_imports() -> None:
    """No MCP server file may still import from the deleted portal_mcp.mcp_server path."""
    import subprocess

    result = subprocess.run(
        ["grep", "-rl", "from portal_mcp.mcp_server", "portal_mcp/"],
        capture_output=True,
        text=True,
    )
    hits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert not hits, (
        f"Vendored mcp_server import still present in: {hits}\n"
        "Replace the stale vendored import with `from mcp.server import MCPServer`."
    )
