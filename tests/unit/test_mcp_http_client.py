"""Unit tests for the Pipeline's feature-gated native MCP client."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

import httpx
import pytest

from portal.platform.inference import mcp_http
from portal.platform.inference import tool_registry as registry_module
from portal.platform.inference.config import (
    PortalConfig,
    get_pipeline_mcp_client_modes,
    load_portal_config,
)
from portal.platform.inference.mcp_http import MCPHTTPError, call_tool, list_tools, map_tool_result


def _response(request_id: str, result: dict[str, Any], status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"jsonrpc": "2.0", "id": request_id, "result": result},
    )


@pytest.fixture(autouse=True)
def _clear_protocol_cache():
    mcp_http._SERVER_STATES.clear()
    mcp_http._SERVER_LOCKS.clear()
    yield
    mcp_http._SERVER_STATES.clear()
    mcp_http._SERVER_LOCKS.clear()


@pytest.mark.asyncio
async def test_list_tools_sends_modern_metadata_and_follows_cursors() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        cursor = body["params"].get("cursor")
        page = (
            {"tools": [{"name": "second"}]}
            if cursor
            else {
                "tools": [{"name": "first"}],
                "nextCursor": "page-2",
            }
        )
        return _response(body["id"], page)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tools = await list_tools(client, "http://pipeline.test/", timeout_s=2)

    assert [tool["name"] for tool in tools] == ["first", "second"]
    assert [request.url.path for request in requests] == ["/mcp", "/mcp"]
    for request in requests:
        body = json.loads(request.content)
        assert body["method"] == "tools/list"
        assert request.headers["Mcp-Method"] == "tools/list"
        assert request.headers["MCP-Protocol-Version"] == "2026-07-28"
        assert body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
        assert body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"] == {}


@pytest.mark.asyncio
async def test_call_tool_parses_sse_and_sets_mcp_name_header() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["Mcp-Method"] == "tools/call"
        assert request.headers["Mcp-Name"] == "get_pipeline_status"
        assert body["params"]["name"] == "get_pipeline_status"
        assert body["params"]["arguments"] == {"verbose": True}
        progress = {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}
        result = {
            "resultType": "complete",
            "content": [{"type": "text", "text": "ok"}],
            "structuredContent": {"status": "ok"},
        }
        events = [
            f"event: message\ndata: {json.dumps(progress)}\n\n",
            f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': body['id'], 'result': result})}\n\n",
        ]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text="".join(events)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await call_tool(
            client,
            "http://pipeline.test",
            "get_pipeline_status",
            {"verbose": True},
            timeout_s=2,
        )

    assert result["structuredContent"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_jsonrpc_errors_are_preserved_even_on_http_error_status() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            400,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "error": {"code": -32602, "message": "Invalid params"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MCPHTTPError, match="Invalid params") as raised:
            await call_tool(client, "http://pipeline.test", "x", {}, timeout_s=2)

    assert raised.value.code == -32602


@pytest.mark.asyncio
async def test_call_tool_cancellation_propagates_to_the_http_request() -> None:
    started = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("cancelled request continued")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(call_tool(client, "http://pipeline.test", "x", {}, 10))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_tool_registry_uses_configured_native_mcp_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return _response(
                body["id"],
                {
                    "tools": [
                        {
                            "name": "get_pipeline_status",
                            "description": "health",
                            "inputSchema": {"type": "object", "properties": {}},
                        }
                    ]
                },
            )
        return _response(
            body["id"],
            {"resultType": "complete", "content": [{"type": "text", "text": "ok"}]},
        )

    monkeypatch.setattr(registry_module, "MCP_CLIENT_MODES", {"pipeline": "native"})
    monkeypatch.setattr(registry_module, "MCP_SERVERS", {"pipeline": "http://pipeline.test"})
    registry = registry_module.ToolRegistry()
    registry._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    await registry.refresh(force=True)
    result = await registry.dispatch("get_pipeline_status", {})
    await registry.close()

    assert registry.get("get_pipeline_status") is not None
    assert result == "ok"
    assert [json.loads(request.content)["method"] for request in requests] == [
        "tools/list",
        "tools/call",
    ]


@pytest.mark.asyncio
async def test_legacy_server_falls_back_once_and_caches_its_session() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        method = body["method"]
        if method == "tools/list" and request.headers.get("MCP-Protocol-Version") == "2026-07-28":
            return httpx.Response(
                400,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32022, "message": "Unsupported protocol version"},
                },
            )
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "legacy-session"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "serverInfo": {},
                    },
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        assert request.headers["Mcp-Session-Id"] == "legacy-session"
        assert "_meta" not in body.get("params", {})
        if method == "tools/list":
            return _response(body["id"], {"tools": [{"name": "legacy_tool"}]})
        return _response(body["id"], {"content": [{"type": "text", "text": '{"ok": true}'}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tools = await list_tools(client, "http://legacy.test", timeout_s=2)
        result = await call_tool(client, "http://legacy.test", "legacy_tool", {}, timeout_s=2)

    assert [tool["name"] for tool in tools] == ["legacy_tool"]
    assert map_tool_result(result) == {"ok": True}
    assert [json.loads(request.content)["method"] for request in requests] == [
        "tools/list",
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]
    legacy_requests = requests[3:]
    assert all(
        request.headers["MCP-Protocol-Version"] == "2025-11-25" for request in legacy_requests
    )
    assert all("Mcp-Method" not in request.headers for request in legacy_requests)


@pytest.mark.asyncio
async def test_legacy_session_404_reinitializes_and_retries_once() -> None:
    init_count = 0
    expired_session_seen = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal init_count, expired_session_seen
        body = json.loads(request.content)
        method = body["method"]
        if method == "tools/list" and request.headers.get("MCP-Protocol-Version") == "2026-07-28":
            return httpx.Response(
                400,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32022, "message": "Unsupported protocol version"},
                },
            )
        if method == "initialize":
            init_count += 1
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": f"session-{init_count}"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "serverInfo": {},
                    },
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        session = request.headers["Mcp-Session-Id"]
        if session == "session-1" and not expired_session_seen:
            expired_session_seen = True
            return httpx.Response(404, text="session expired")
        assert session == "session-2"
        return _response(body["id"], {"tools": [{"name": "legacy_tool"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tools = await list_tools(client, "http://expired.test", timeout_s=2)

    assert [tool["name"] for tool in tools] == ["legacy_tool"]
    assert init_count == 2


@pytest.mark.asyncio
async def test_legacy_request_timeout_and_cancellation_propagate() -> None:
    started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body["method"]
        if method == "tools/list" and request.headers.get("MCP-Protocol-Version") == "2026-07-28":
            return httpx.Response(
                400,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32022, "message": "Unsupported protocol version"},
                },
            )
        if method == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "serverInfo": {},
                    },
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("cancelled request continued")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(list_tools(client, "http://cancel-legacy.test", timeout_s=10))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_legacy_request_timeout_uses_the_call_deadline() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body["method"]
        if method == "tools/list" and request.headers.get("MCP-Protocol-Version") == "2026-07-28":
            return httpx.Response(
                400,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32022, "message": "Unsupported protocol version"},
                },
            )
        if method == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "serverInfo": {},
                    },
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        await asyncio.Event().wait()
        raise AssertionError("timed-out request continued")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TimeoutError):
            await list_tools(client, "http://timeout-legacy.test", timeout_s=0.05)


def test_native_tool_result_maps_to_raw_rest_json() -> None:
    assert map_tool_result(
        {"structuredContent": [1, 2], "content": [{"type": "text", "text": "ignored"}]}
    ) == [1, 2]
    assert map_tool_result({"content": [{"type": "text", "text": '{"count": 3}'}]}) == {"count": 3}
    assert map_tool_result({"content": [{"type": "text", "text": "plain"}]}) == "plain"
    assert (
        map_tool_result(
            {
                "content": [
                    {"type": "text", "text": "first"},
                    {"type": "image", "data": "unused"},
                    {"type": "text", "text": "second"},
                ]
            }
        )
        == "first\nsecond"
    )


def test_pipeline_client_mode_is_per_server_and_defaults_to_rest() -> None:
    config = load_portal_config()
    modes = get_pipeline_mcp_client_modes(config)
    # pipeline passed live native/REST parity on 2026-10-23; the rest stay on REST until they do.
    assert modes["pipeline"] == "native"
    assert modes["documents"] == "rest"

    raw = config.model_dump()
    entry = next(server for server in raw["mcp_fleet"] if server["id"] == "documents")
    entry.pop("pipeline_client", None)
    assert get_pipeline_mcp_client_modes(PortalConfig.model_validate(raw))["documents"] == "rest"


@pytest.mark.asyncio
async def test_native_is_error_returns_rest_error_shape_and_trips_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return _response(body["id"], {"tools": [{"name": "failing_tool"}]})
        return _response(
            body["id"], {"isError": True, "content": [{"type": "text", "text": "tool failed"}]}
        )

    monkeypatch.setattr(registry_module, "MCP_CLIENT_MODES", {"pipeline": "native"})
    monkeypatch.setattr(registry_module, "MCP_SERVERS", {"pipeline": "http://error.test"})
    registry = registry_module.ToolRegistry()
    registry._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await registry.refresh(force=True)
    result = await registry.dispatch("failing_tool", {})
    tool = registry.get("failing_tool")
    await registry.close()

    assert result == {
        "error": "Tool 'failing_tool' returned an MCP tool error",
        "detail": "tool failed",
    }
    assert tool is not None and tool.healthy is False and tool.consecutive_failures == 1


def _schema_signature(tools: list[Any], schema_key: str) -> dict[str, set[str]]:
    """Return each tool's required argument names from an MCP schema collection."""
    signatures = {}
    for tool in tools:
        raw = (
            tool.model_dump(mode="json", exclude_none=True) if hasattr(tool, "model_dump") else tool
        )
        schema = raw.get(schema_key) or {}
        signatures[raw["name"]] = set(schema.get("required", []))
    return signatures


@pytest.mark.skipif(importlib.util.find_spec("mcp") is None, reason="MCP SDK is not installed")
def test_pipeline_mcp_native_tools_list_matches_rest_manifest() -> None:
    from portal.platform.mcp_host import pipeline_mcp

    native_tools = asyncio.run(pipeline_mcp.mcp.list_tools())
    rest_tools = pipeline_mcp.TOOLS_MANIFEST

    assert _schema_signature(native_tools, "input_schema") == _schema_signature(
        rest_tools, "parameters"
    )


def test_map_tool_result_unwraps_sdk_wrapped_non_object_returns() -> None:
    from portal.platform.inference.mcp_http import map_tool_result

    wrapped_schema = {
        "type": "object",
        "properties": {"result": {"type": "array"}},
        "required": ["result"],
    }
    result = {"structuredContent": {"result": [{"name": "m"}]}, "content": [], "isError": False}
    assert map_tool_result(result, wrapped_schema) == [{"name": "m"}]
    # An object tool that happens to return a "result" key is left alone without the schema.
    assert map_tool_result(result) == {"result": [{"name": "m"}]}
    obj = {"structuredContent": {"status": "ok"}, "content": []}
    assert map_tool_result(obj, {"type": "object", "additionalProperties": True}) == {
        "status": "ok"
    }
