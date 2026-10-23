"""Test exponential backoff for tool health in ToolRegistry."""

import time
from unittest.mock import patch

import pytest

from portal.platform.inference import tool_registry as registry_module
from portal.platform.inference.mcp_http import MCPHTTPError
from portal.platform.inference.tool_registry import ToolDefinition, ToolRegistry, _backoff_seconds

# ── _backoff_seconds schedule ────────────────────────────────────────────────


def test_backoff_schedule():
    assert _backoff_seconds(1) == 30
    assert _backoff_seconds(2) == 120
    assert _backoff_seconds(3) == 300
    assert _backoff_seconds(4) == 900
    assert _backoff_seconds(5) == 3600
    assert _backoff_seconds(99) == 3600  # capped


# ── dispatch: success resets backoff state ───────────────────────────────────


@pytest.mark.asyncio
async def test_success_resets_backoff():
    reg = ToolRegistry()
    tool = ToolDefinition(
        name="my_tool",
        description="",
        parameters={},
        server_id="test",
        server_url="http://localhost:9999",
        healthy=False,
        consecutive_failures=3,
        next_retry_at=0.0,
    )
    reg._tools["my_tool"] = tool

    async def fake_call_tool(*_a, **_k):
        return {"content": [{"type": "text", "text": '{"result": "ok"}'}]}

    with patch.object(registry_module, "call_tool", fake_call_tool):
        result = await reg.dispatch("my_tool", {})

    assert result == {"result": "ok"}
    assert tool.healthy is True
    assert tool.consecutive_failures == 0
    assert tool.next_retry_at == 0.0


# ── dispatch: single failure schedules 30s retry ────────────────────────────


@pytest.mark.asyncio
async def test_single_failure_schedules_30s():
    reg = ToolRegistry()
    tool = ToolDefinition(
        name="my_tool",
        description="",
        parameters={},
        server_id="test",
        server_url="http://localhost:9999",
    )
    reg._tools["my_tool"] = tool

    async def fake_call_tool(*_a, **_k):
        raise MCPHTTPError("MCP returned HTTP 503", status_code=503)

    t_before = time.time()
    with patch.object(registry_module, "call_tool", fake_call_tool):
        result = await reg.dispatch("my_tool", {})

    assert "HTTP 503" in result["error"]
    assert tool.healthy is False
    assert tool.consecutive_failures == 1
    assert tool.next_retry_at >= t_before + 29  # ~30s


# ── dispatch: three failures schedules 5m retry ─────────────────────────────


@pytest.mark.asyncio
async def test_three_failures_schedules_5m():
    reg = ToolRegistry()
    tool = ToolDefinition(
        name="my_tool",
        description="",
        parameters={},
        server_id="test",
        server_url="http://localhost:9999",
        healthy=False,
        consecutive_failures=2,
        next_retry_at=0.0,
    )
    reg._tools["my_tool"] = tool

    async def fake_call_tool(*_a, **_k):
        raise MCPHTTPError("MCP returned HTTP 500", status_code=500)

    t_before = time.time()
    with patch.object(registry_module, "call_tool", fake_call_tool):
        await reg.dispatch("my_tool", {})

    assert tool.consecutive_failures == 3
    assert tool.next_retry_at >= t_before + 299  # ~300s = 5m


# ── dispatch: blocked inside backoff window ──────────────────────────────────


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


# ── dispatch: allowed after backoff window expires ───────────────────────────


@pytest.mark.asyncio
async def test_allowed_after_backoff_window():
    reg = ToolRegistry()
    tool = ToolDefinition(
        name="my_tool",
        description="",
        parameters={},
        server_id="test",
        server_url="http://localhost:9999",
        healthy=False,
        consecutive_failures=1,
        next_retry_at=time.time() - 1,  # expired
    )
    reg._tools["my_tool"] = tool

    async def fake_call_tool(*_a, **_k):
        return {"content": [{"type": "text", "text": '{"result": "recovered"}'}]}

    with patch.object(registry_module, "call_tool", fake_call_tool):
        result = await reg.dispatch("my_tool", {})

    assert result == {"result": "recovered"}
    assert tool.healthy is True


# ── get_openai_tools: unhealthy tool excluded while in backoff ───────────────


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
