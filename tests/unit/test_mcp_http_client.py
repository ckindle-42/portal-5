"""Unit tests for the Pipeline's native MCP client."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

import httpx
import pytest

from portal.platform.inference import mcp_http
from portal.platform.inference import tool_registry as registry_module
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
        assert body["params"]["_meta"]["portal5/request_id"] == "request-7"
        assert body["params"]["_meta"]["portal5/eval"]["run"].startswith("wfe_")
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
            metadata={
                "portal5/request_id": "request-7",
                "portal5/eval": {
                    "campaign": "wfe_aaaaaaaaaaaaaaaa",
                    "run": "wfe_bbbbbbbbbbbbbbbb",
                    "allow": ["get_pipeline_status"],
                },
            },
        )

    assert result["structuredContent"] == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [307, 308])
async def test_call_tool_follows_same_origin_redirect_and_keeps_the_post(status_code: int) -> None:
    """mlx-transcribe answers /mcp with a redirect to /mcp/; the body must survive."""
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        if request.url.path == "/mcp":
            return httpx.Response(status_code, headers={"location": "/mcp/"})
        assert request.method == "POST"
        assert body["params"]["arguments"] == {"file_path": "a.wav"}
        return _response(body["id"], {"structuredContent": {"ok": True}, "content": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await call_tool(
            client, "http://127.0.0.1:8924", "transcribe_audio", {"file_path": "a.wav"}, timeout_s=2
        )

    assert result["structuredContent"] == {"ok": True}
    assert [request.url.path for request in seen] == ["/mcp", "/mcp/"]
    assert all(request.method == "POST" for request in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "location"),
    [(307, "http://evil.test/mcp"), (302, "/mcp/")],
)
async def test_call_tool_does_not_follow_cross_origin_or_method_changing_redirects(
    status_code: int, location: str
) -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status_code, headers={"location": location})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MCPHTTPError):
            await call_tool(client, "http://127.0.0.1:8924", "transcribe_audio", {}, timeout_s=2)

    assert [request.url.path for request in seen] == ["/mcp"]


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
                            "_meta": {"portal5/timeout_s": 120},
                        }
                    ]
                },
            )
        return _response(
            body["id"],
            {"resultType": "complete", "content": [{"type": "text", "text": "ok"}]},
        )

    monkeypatch.setattr(registry_module, "MCP_SERVERS", {"pipeline": "http://pipeline.test"})
    registry = registry_module.ToolRegistry()
    registry._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    await registry.refresh(force=True)
    result = await registry.dispatch("get_pipeline_status", {})
    await registry.close()

    assert registry.get("get_pipeline_status") is not None
    assert registry.get("get_pipeline_status").custom_timeout_s == 120.0
    assert result == "ok"
    assert [json.loads(request.content)["method"] for request in requests] == [
        "tools/list",
        "tools/call",
    ]


@pytest.mark.asyncio
async def test_native_scoped_compliance_routes_to_eval_and_forwards_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portal.platform.inference.tool_registry import ToolDefinition, ToolRegistry
    from portal.platform.mcp_host import eval_scope

    scope = {
        "campaign": "wfe_aaaaaaaaaaaaaaaa",
        "run": "wfe_bbbbbbbbbbbbbbbb",
        "allow": ["compliance_read"],
    }
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        return _response(
            body["id"],
            {
                "resultType": "complete",
                "content": [],
                "structuredContent": {"ok": True},
            },
        )

    monkeypatch.setenv("MCP_COMPLIANCE_EVAL_URL", "http://compliance-eval.test")
    registry = ToolRegistry()
    registry._tools["compliance_read"] = ToolDefinition(
        name="compliance_read",
        description="read",
        parameters={"type": "object"},
        server_id="compliance",
        server_url="http://compliance.test",
    )
    registry._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    token = eval_scope.EVAL_SCOPE.set(scope)
    try:
        result = await registry.dispatch("compliance_read", {"requirement": "R1"}, "chat-9")
    finally:
        eval_scope.EVAL_SCOPE.reset(token)
        await registry.close()

    body = json.loads(requests[0].content)
    assert result == {"ok": True}
    assert requests[0].url.host == "compliance-eval.test"
    assert requests[0].url.path == "/mcp"
    assert body["params"]["_meta"]["portal5/eval"] == scope
    assert body["params"]["_meta"]["portal5/request_id"] == "chat-9"


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
        if method == "tools/list":
            return _response(body["id"], {"tools": [{"name": "legacy_tool"}]})
        assert body["params"]["_meta"]["portal5/request_id"] == "legacy-req"
        return _response(body["id"], {"content": [{"type": "text", "text": '{"ok": true}'}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tools = await list_tools(client, "http://legacy.test", timeout_s=2)
        result = await call_tool(
            client,
            "http://legacy.test",
            "legacy_tool",
            {},
            timeout_s=2,
            metadata={"portal5/request_id": "legacy-req"},
        )

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


def test_native_tool_result_maps_to_raw_json() -> None:
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


@pytest.mark.skipif(importlib.util.find_spec("mcp") is None, reason="MCP SDK is not installed")
def test_pipeline_mcp_native_tools_list_keeps_its_contract() -> None:
    from portal.platform.mcp_host import pipeline_mcp

    native = asyncio.run(pipeline_mcp.mcp.list_tools())
    signatures = {tool.name: sorted(tool.input_schema.get("required", [])) for tool in native}

    assert signatures == {
        "get_pipeline_status": [],
        "list_workspaces": [],
        "get_loaded_models": [],
        "get_metrics_summary": [],
        "get_workspace_recommendation": ["task"],
        "explore_repository": ["query"],
        "trigger_backend_warmup": [],
        "arm_queue_task": ["discipline", "task_id", "template_key"],
        "read_text_file": ["path"],
        "list_directory": ["path"],
        "search_files": ["pattern"],
        "write_file": ["content", "path"],
    }
    assert all(tool.description for tool in native)


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
