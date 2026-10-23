"""Unit tests for the Pipeline's feature-gated native MCP client."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from portal.platform.inference import tool_registry as registry_module
from portal.platform.inference.mcp_http import MCPHTTPError, call_tool, list_tools


def _response(request_id: str, result: dict[str, Any], status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"jsonrpc": "2.0", "id": request_id, "result": result},
    )


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
async def test_tool_registry_uses_native_mcp_only_for_gated_pipeline_server(
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

    monkeypatch.setattr(registry_module, "PIPELINE_NATIVE_MCP_CLIENT", True)
    monkeypatch.setattr(registry_module, "MCP_SERVERS", {"pipeline": "http://pipeline.test"})
    registry = registry_module.ToolRegistry()
    registry._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    await registry.refresh(force=True)
    result = await registry.dispatch("get_pipeline_status", {})
    await registry.close()

    assert registry.get("get_pipeline_status") is not None
    assert result["resultType"] == "complete"
    assert [json.loads(request.content)["method"] for request in requests] == [
        "tools/list",
        "tools/call",
    ]
