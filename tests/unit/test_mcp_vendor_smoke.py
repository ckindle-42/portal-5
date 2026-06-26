"""Smoke test for the FastMCP import path after de-vendoring (M4).

After Branch A (de-vendor), all MCP servers import FastMCP from upstream
mcp.server.fastmcp. This test verifies:
- FastMCP is importable from the canonical upstream location.
- A server can be instantiated, a tool registered, and the tool listed.
- The server exposes an HTTP app factory (needed for streamable-http transport).
- No reference to the deleted portal_mcp.mcp_server vendored path survives.
"""

from __future__ import annotations

import inspect


def test_fastmcp_import_from_upstream() -> None:
    """FastMCP must come from upstream mcp.server.fastmcp, not the deleted vendor tree."""
    from mcp.server.fastmcp import FastMCP

    assert FastMCP is not None
    mod = inspect.getmodule(FastMCP)
    assert mod is not None
    assert "portal_mcp.mcp_server" not in (mod.__name__ or ""), (
        f"FastMCP is still coming from the vendored path: {mod.__name__}"
    )
    assert "mcp" in (mod.__file__ or ""), f"Unexpected FastMCP module file: {mod.__file__}"


def test_fastmcp_tool_registration() -> None:
    """Instantiate FastMCP, register a trivial tool, assert it appears in the tool list."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name="smoke-test")

    @server.tool()
    def echo(message: str) -> str:
        """Echo the input."""
        return message

    tools = server._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    assert "echo" in tool_names, f"Registered tool not found; got: {tool_names}"


def test_fastmcp_http_app_factory() -> None:
    """FastMCP instance must expose a streamable-http ASGI app."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name="smoke-http")
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
        "Run: sed -i 's/from portal_mcp.mcp_server.fastmcp import/from mcp.server.fastmcp import/g'"
    )
