"""Unit tests for the Pipeline's native MCP client."""

from __future__ import annotations

import asyncio
import importlib.util
import json

import httpx
import pytest

from portal.platform.inference import mcp_http
from portal.platform.inference.mcp_http import map_tool_result


@pytest.fixture(autouse=True)
def _clear_protocol_cache():
    mcp_http._SERVER_STATES.clear()
    mcp_http._SERVER_LOCKS.clear()
    yield
    mcp_http._SERVER_STATES.clear()
    mcp_http._SERVER_LOCKS.clear()


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
        "jarvis_submit": ["text", "user_id"],
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


@pytest.mark.asyncio
async def test_mcp_call_can_stream_past_its_old_total_budget() -> None:
    class SlowChunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(0.04)
            yield first
            await asyncio.sleep(0.04)
            yield second

    def handler(request: httpx.Request) -> httpx.Response:
        request_id = json.loads(request.content)["id"]
        wire = (
            "data: "
            + json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"structuredContent": {"ok": True}, "isError": False},
                }
            )
            + "\n\n"
        ).encode()
        split = len(wire) // 2
        nonlocal first, second
        first, second = wire[:split], wire[split:]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=SlowChunks()
        )

    first = second = b""
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await mcp_http.call_tool(client, "http://mcp", "long_tool", {}, 0.06)

    assert result["structuredContent"] == {"ok": True}


@pytest.mark.asyncio
async def test_mcp_call_fails_when_response_stream_stalls() -> None:
    idle_timeout_s = 0.02

    class Stalled(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(idle_timeout_s)
            raise httpx.ReadTimeout("no response bytes")
            yield b""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Stalled())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        started = asyncio.get_running_loop().time()
        with pytest.raises(httpx.ReadTimeout, match="no response bytes"):
            await mcp_http.call_tool(client, "http://mcp", "stalled_tool", {}, idle_timeout_s)

    assert asyncio.get_running_loop().time() - started >= idle_timeout_s
