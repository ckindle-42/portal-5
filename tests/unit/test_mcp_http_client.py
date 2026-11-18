"""Unit tests for the Pipeline's native MCP client."""

from __future__ import annotations

import asyncio
import importlib.util

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
