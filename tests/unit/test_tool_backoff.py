"""Test exponential backoff for tool health in ToolRegistry."""

import time

import pytest

from portal.platform.inference.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    _backoff_seconds,
    _is_mcp_crash_text,
    _tool_error_is_infra,
)


def test_backoff_schedule():
    assert _backoff_seconds(1) == 30
    assert _backoff_seconds(2) == 120
    assert _backoff_seconds(3) == 300
    assert _backoff_seconds(4) == 900
    assert _backoff_seconds(5) == 3600
    assert _backoff_seconds(99) == 3600  # capped


@pytest.mark.asyncio
async def test_blocked_inside_backoff_window():
    reg = ToolRegistry()
    tool = ToolDefinition(
        name="my_tool",
        description="",
        parameters={},
        server_id="test",
        server_url="http://localhost:9999",
        healthy=False,
        consecutive_failures=1,
        next_retry_at=time.time() + 999,
    )
    reg._tools["my_tool"] = tool

    result = await reg.dispatch("my_tool", {})
    assert "backoff" in result["error"]
    assert "consecutive failures" in result["error"]


def test_get_openai_tools_excludes_in_backoff():
    reg = ToolRegistry()
    reg._tools["good_tool"] = ToolDefinition(
        name="good_tool",
        description="ok",
        parameters={},
        server_id="s1",
        server_url="http://localhost:1",
        healthy=True,
    )
    reg._tools["bad_tool"] = ToolDefinition(
        name="bad_tool",
        description="broken",
        parameters={},
        server_id="s2",
        server_url="http://localhost:2",
        healthy=False,
        consecutive_failures=1,
        next_retry_at=time.time() + 999,
    )
    reg._tools["recovering_tool"] = ToolDefinition(
        name="recovering_tool",
        description="expired backoff",
        parameters={},
        server_id="s3",
        server_url="http://localhost:3",
        healthy=False,
        consecutive_failures=1,
        next_retry_at=time.time() - 1,  # window expired
    )

    tools = reg.get_openai_tools(["good_tool", "bad_tool", "recovering_tool"])
    names = [t["function"]["name"] for t in tools]
    assert "good_tool" in names
    assert "recovering_tool" in names  # expired backoff = allowed
    assert "bad_tool" not in names  # still in backoff window


_VALIDATION = (
    "Error executing tool execute_bash: 1 validation error for execute_bashArguments\n"
    "code\n  Field required [type=missing, input_value={'command': 'echo hi'}, input_type=dict]"
)


def test_crash_line_is_infra_and_validation_text_is_not():
    assert _is_mcp_crash_text("execute_bash", "Error executing tool execute_bash")
    assert _is_mcp_crash_text(
        "execute_bash",
        "Error executing tool execute_bash: Error executing tool inner",
    )
    assert not _is_mcp_crash_text("execute_bash", _VALIDATION)
    assert not _tool_error_is_infra("execute_bash", {"detail": _VALIDATION})
    assert _tool_error_is_infra("execute_bash", {"detail": "Error executing tool execute_bash"})
