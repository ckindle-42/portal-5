"""Small stateless MCP Streamable HTTP client for Pipeline tool calls."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx

PROTOCOL_VERSION = "2026-07-28"
_CLIENT_INFO = {"name": "portal-pipeline", "version": "1.0.0"}
_PROTOCOL_KEY = "io.modelcontextprotocol/protocolVersion"
_CLIENT_KEY = "io.modelcontextprotocol/clientInfo"
_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"


class MCPHTTPError(RuntimeError):
    """An MCP JSON-RPC or Streamable HTTP response error."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def _messages(response: httpx.Response) -> list[dict[str, Any]]:
    """Decode JSON or SSE JSON-RPC messages from one Streamable HTTP response."""
    try:
        if "text/event-stream" in response.headers.get("content-type", ""):
            messages = []
            for event in response.text.replace("\r\n", "\n").split("\n\n"):
                data = [
                    line[5:].lstrip() for line in event.splitlines() if line.startswith("data:")
                ]
                if data:
                    messages.append(json.loads("\n".join(data)))
        else:
            messages = [response.json()]
    except (json.JSONDecodeError, ValueError) as exc:
        raise MCPHTTPError(f"MCP returned invalid JSON: {exc}") from exc
    if not all(isinstance(message, dict) for message in messages):
        raise MCPHTTPError("MCP returned a non-object JSON-RPC message")
    return messages


async def _request(
    client: httpx.AsyncClient,
    base_url: str,
    method: str,
    params: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    """Send one current-revision MCP request and return its result object."""
    request_id = str(uuid.uuid4())
    request_params = {
        **params,
        "_meta": {
            _PROTOCOL_KEY: PROTOCOL_VERSION,
            _CLIENT_KEY: _CLIENT_INFO,
            _CAPABILITIES_KEY: {},
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if isinstance(params.get("name"), str):
        headers["Mcp-Name"] = params["name"]
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": request_params}
    response = await asyncio.wait_for(
        client.post(f"{base_url.rstrip('/')}/mcp", json=payload, headers=headers, timeout=None),
        timeout=timeout_s,
    )
    for message in _messages(response):
        if message.get("id") != request_id:
            continue
        error = message.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            detail = error.get("message", "MCP JSON-RPC error")
            raise MCPHTTPError(str(detail), code if isinstance(code, int) else None)
        result = message.get("result")
        if isinstance(result, dict):
            if response.status_code >= 400:
                raise MCPHTTPError(f"MCP returned HTTP {response.status_code}")
            return result
        raise MCPHTTPError("MCP response did not contain a result object")
    detail = response.text[:200] or f"HTTP {response.status_code} without a JSON-RPC response"
    raise MCPHTTPError(f"MCP response did not match request {request_id}: {detail}")


async def list_tools(
    client: httpx.AsyncClient, base_url: str, timeout_s: float
) -> list[dict[str, Any]]:
    """List every tool exposed by a current-revision Streamable HTTP server."""
    tools: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        params = {"cursor": cursor} if cursor else {}
        result = await _request(client, base_url, "tools/list", params, timeout_s)
        page = result.get("tools", [])
        if not isinstance(page, list) or not all(isinstance(tool, dict) for tool in page):
            raise MCPHTTPError("MCP tools/list returned an invalid tools list")
        tools.extend(page)
        next_cursor = result.get("nextCursor")
        if next_cursor is None:
            return tools
        if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
            raise MCPHTTPError("MCP tools/list returned an invalid or repeated cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor


async def call_tool(
    client: httpx.AsyncClient,
    base_url: str,
    name: str,
    arguments: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    """Call one MCP tool and preserve its standard content and structured result."""
    result = await _request(
        client, base_url, "tools/call", {"name": name, "arguments": arguments}, timeout_s
    )
    if result.get("resultType") in {"input_required", "task"}:
        raise MCPHTTPError(f"MCP {result['resultType']} responses are not enabled in this client")
    return result
