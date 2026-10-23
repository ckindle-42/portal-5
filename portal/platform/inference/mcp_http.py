"""Small dual-era MCP Streamable HTTP client for Pipeline tool calls."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx

PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
_CLIENT_INFO = {"name": "portal-pipeline", "version": "1.0.0"}
_PROTOCOL_KEY = "io.modelcontextprotocol/protocolVersion"
_CLIENT_KEY = "io.modelcontextprotocol/clientInfo"
_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"


class MCPHTTPError(RuntimeError):
    """An MCP JSON-RPC or Streamable HTTP response error."""

    def __init__(
        self, message: str, code: int | None = None, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass
class _ServerState:
    era: Literal["modern", "legacy"]
    protocol_version: str | None = None
    session_id: str | None = None


_SERVER_STATES: dict[str, _ServerState] = {}
_SERVER_LOCKS: dict[str, asyncio.Lock] = {}


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
        detail = response.text[:200] or str(exc)
        raise MCPHTTPError(
            f"MCP returned invalid JSON: {detail}", status_code=response.status_code
        ) from exc
    if not all(isinstance(message, dict) for message in messages):
        raise MCPHTTPError(
            "MCP returned a non-object JSON-RPC message", status_code=response.status_code
        )
    return messages


def _response_result(response: httpx.Response, request_id: str) -> dict[str, Any]:
    """Extract one matching JSON-RPC result or raise its wire error."""
    for message in _messages(response):
        if message.get("id") != request_id:
            continue
        error = message.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            detail = error.get("message", "MCP JSON-RPC error")
            raise MCPHTTPError(
                str(detail), code if isinstance(code, int) else None, response.status_code
            )
        result = message.get("result")
        if isinstance(result, dict):
            if response.status_code >= 400:
                raise MCPHTTPError(
                    f"MCP returned HTTP {response.status_code}", status_code=response.status_code
                )
            return result
        raise MCPHTTPError(
            "MCP response did not contain a result object", status_code=response.status_code
        )
    detail = response.text[:200] or f"HTTP {response.status_code} without a JSON-RPC response"
    raise MCPHTTPError(
        f"MCP response did not match request {request_id}: {detail}",
        status_code=response.status_code,
    )


async def _post(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    deadline: float,
) -> httpx.Response:
    """Post one message within the current operation's remaining timeout."""
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError
    return await asyncio.wait_for(
        client.post(url, json=payload, headers=headers, timeout=None), timeout=remaining
    )


def _modern_headers(method: str, params: dict[str, Any]) -> dict[str, str]:
    """Headers for one stateless 2026-07-28 request."""
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if isinstance(params.get("name"), str):
        headers["Mcp-Name"] = params["name"]
    return headers


async def _modern_request(
    client: httpx.AsyncClient,
    url: str,
    method: str,
    params: dict[str, Any],
    deadline: float,
) -> dict[str, Any]:
    """Send one current-revision MCP request."""
    request_id = str(uuid.uuid4())
    request_params = {
        **params,
        "_meta": {
            _PROTOCOL_KEY: PROTOCOL_VERSION,
            _CLIENT_KEY: _CLIENT_INFO,
            _CAPABILITIES_KEY: {},
        },
    }
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": request_params}
    response = await _post(client, url, payload, _modern_headers(method, params), deadline)
    return _response_result(response, request_id)


def _is_legacy_response(error: MCPHTTPError) -> bool:
    """Recognize a response that asks this client to use the legacy lifecycle."""
    if error.code in {-32022, -32600, -32601} or error.status_code == 406:
        return True
    detail = str(error).lower()
    return error.status_code == 400 and any(
        marker in detail
        for marker in ("protocol", "unsupported", "not initialized", "initialize", "session")
    )


def _legacy_headers(state: _ServerState, session: bool = True) -> dict[str, str]:
    """Headers for one negotiated legacy request."""
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": state.protocol_version or LEGACY_PROTOCOL_VERSION,
    }
    if session and state.session_id:
        headers["Mcp-Session-Id"] = state.session_id
    return headers


async def _initialize_legacy(client: httpx.AsyncClient, url: str, deadline: float) -> _ServerState:
    """Initialize a 2025-11-25 session and notify the server it is ready."""
    request_id = str(uuid.uuid4())
    params = {
        "protocolVersion": LEGACY_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": _CLIENT_INFO,
    }
    payload = {"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": params}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    response = await _post(client, url, payload, headers, deadline)
    result = _response_result(response, request_id)
    protocol_version = result.get("protocolVersion")
    if not isinstance(protocol_version, str):
        raise MCPHTTPError("MCP initialize returned no protocol version")
    state = _ServerState("legacy", protocol_version, response.headers.get("Mcp-Session-Id"))
    notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    response = await _post(client, url, notification, _legacy_headers(state), deadline)
    if response.status_code >= 400:
        detail = response.text[:200]
        raise MCPHTTPError(
            f"MCP initialized notification returned HTTP {response.status_code}: {detail}",
            status_code=response.status_code,
        )
    return state


async def _legacy_request(
    client: httpx.AsyncClient,
    key: str,
    url: str,
    method: str,
    params: dict[str, Any],
    deadline: float,
    state: _ServerState,
    lock: asyncio.Lock,
    retry_expired: bool = True,
) -> dict[str, Any]:
    """Send one legacy request, reinitializing once after a session expiry."""
    request_id = str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {key: value for key, value in params.items() if key != "_meta"},
    }
    response = await _post(client, url, payload, _legacy_headers(state), deadline)
    if response.status_code == 404 and retry_expired:
        async with lock:
            current = _SERVER_STATES.get(key)
            if current is None or current.session_id == state.session_id:
                current = await _initialize_legacy(client, url, deadline)
                _SERVER_STATES[key] = current
        return await _legacy_request(
            client, key, url, method, params, deadline, current, lock, retry_expired=False
        )
    return _response_result(response, request_id)


async def _request(
    client: httpx.AsyncClient,
    base_url: str,
    method: str,
    params: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    """Send one request using the protocol era cached for its server URL."""
    key = base_url.rstrip("/")
    url = f"{key}/mcp"
    deadline = asyncio.get_running_loop().time() + timeout_s
    lock = _SERVER_LOCKS.setdefault(key, asyncio.Lock())
    state = _SERVER_STATES.get(key)
    if state is None:
        async with lock:
            state = _SERVER_STATES.get(key)
            if state is None:
                try:
                    result = await _modern_request(client, url, method, params, deadline)
                except MCPHTTPError as exc:
                    if not _is_legacy_response(exc):
                        raise
                    state = await _initialize_legacy(client, url, deadline)
                    _SERVER_STATES[key] = state
                else:
                    _SERVER_STATES[key] = _ServerState("modern")
                    return result
    if state is not None and state.era == "modern":
        try:
            return await _modern_request(client, url, method, params, deadline)
        except MCPHTTPError as exc:
            if not _is_legacy_response(exc):
                raise
            async with lock:
                state = _SERVER_STATES.get(key)
                if state is None or state.era == "modern":
                    state = await _initialize_legacy(client, url, deadline)
                    _SERVER_STATES[key] = state
    if state is None:
        raise MCPHTTPError("MCP client protocol state is unavailable")
    return await _legacy_request(client, key, url, method, params, deadline, state, lock)


async def list_tools(
    client: httpx.AsyncClient, base_url: str, timeout_s: float
) -> list[dict[str, Any]]:
    """List every tool exposed by a Streamable HTTP server."""
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
    """Call one MCP tool and preserve its standard result object."""
    result = await _request(
        client, base_url, "tools/call", {"name": name, "arguments": arguments}, timeout_s
    )
    if result.get("resultType") in {"input_required", "task"}:
        raise MCPHTTPError(f"MCP {result['resultType']} responses are not enabled in this client")
    return result


def map_tool_result(result: dict[str, Any]) -> Any:
    """Map a CallToolResult to the raw JSON value returned by REST tool routes."""
    if "structuredContent" in result:
        return result["structuredContent"]
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    texts = [
        item["text"]
        for item in content
        if isinstance(item, dict)
        and item.get("type") == "text"
        and isinstance(item.get("text"), str)
    ]
    if len(content) == 1 and len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]
    return "\n".join(texts)
