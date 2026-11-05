"""Test exponential backoff for tool health in ToolRegistry."""

import time
from unittest.mock import patch

import httpx
import pytest

from portal.platform.inference import tool_registry as registry_module
from portal.platform.inference.mcp_http import MCPHTTPError
from portal.platform.inference.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    _backoff_seconds,
    _is_mcp_crash_text,
    _tool_error_is_infra,
)

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


# ── caller faults do not arm the per-tool breaker ───────────────────────────

_BASH_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "timeout": {"type": "integer"},
    },
    "required": ["code"],
}

_VALIDATION = (
    "Error executing tool execute_bash: 1 validation error for execute_bashArguments\n"
    "code\n  Field required [type=missing, input_value={'command': 'echo hi'}, input_type=dict]"
)


def _tool(name: str, schema: dict | None = None) -> tuple[ToolRegistry, ToolDefinition]:
    reg = ToolRegistry()
    tool = ToolDefinition(
        name=name,
        description="",
        parameters=schema or {},
        server_id="test",
        server_url="http://localhost:9999",
    )
    reg._tools[name] = tool
    return reg, tool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail",
    [
        _VALIDATION,
        "Error executing tool render: Input should be a valid integer",
        "Error executing tool render: unexpected keyword argument(s) ['audio_path']",
        "Error executing tool render: Extra inputs are not permitted",
        "Unsupported mesh extension '.xyz'. Supported: ['.obj', '.stl']",
        "unsupported source type: .numbers",
        "Unsupported target 'fbx'. Supported: stl, 3mf, obj, ply",
        "Expected .docx file, got: .txt",
        "Expected .pdf file, got: .png",
    ],
)
async def test_caller_fault_is_error_does_not_trip_backoff(detail: str):
    reg, tool = _tool("render")

    async def fake_call_tool(*_a, **_k):
        return {"isError": True, "content": [{"type": "text", "text": detail}]}

    with patch.object(registry_module, "call_tool", fake_call_tool):
        for _ in range(3):
            result = await reg.dispatch("render", {})

    assert "error" in result
    assert tool.healthy is True
    assert tool.consecutive_failures == 0
    assert tool.next_retry_at == 0.0


@pytest.mark.asyncio
async def test_validation_errors_then_a_good_call_still_runs():
    reg, tool = _tool("execute_bash", _BASH_SCHEMA)
    calls: list[dict] = []

    async def fake_call_tool(_client, _url, name, arguments, _timeout, metadata=None):
        calls.append(arguments)
        if len(calls) < 4:
            return {"isError": True, "content": [{"type": "text", "text": _VALIDATION}]}
        return {"content": [{"type": "text", "text": '{"stdout": "hi"}'}]}

    with patch.object(registry_module, "call_tool", fake_call_tool):
        for _ in range(3):
            await reg.dispatch("execute_bash", {"code": "echo hi"})
        result = await reg.dispatch("execute_bash", {"code": "echo hi"})

    assert result == {"stdout": "hi"}
    assert tool.healthy is True
    assert tool.consecutive_failures == 0
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_mcp_crash_text_still_trips_backoff():
    reg, tool = _tool("execute_bash")

    async def fake_call_tool(*_a, **_k):
        return {
            "isError": True,
            "content": [{"type": "text", "text": "Error executing tool execute_bash"}],
        }

    with patch.object(registry_module, "call_tool", fake_call_tool):
        await reg.dispatch("execute_bash", {})

    assert tool.healthy is False
    assert tool.consecutive_failures == 1


def test_crash_line_is_infra_and_validation_text_is_not():
    assert _is_mcp_crash_text("execute_bash", "Error executing tool execute_bash")
    assert _is_mcp_crash_text(
        "execute_bash",
        "Error executing tool execute_bash: Error executing tool inner",
    )
    assert not _is_mcp_crash_text("execute_bash", _VALIDATION)
    assert not _tool_error_is_infra("execute_bash", {"detail": _VALIDATION})
    assert _tool_error_is_infra("execute_bash", {"detail": "Error executing tool execute_bash"})


@pytest.mark.asyncio
async def test_three_connection_failures_still_open_backoff():
    reg, tool = _tool("execute_bash")
    calls = 0

    async def fake_call_tool(*_a, **_k):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused")

    t_before = time.time()
    with patch.object(registry_module, "call_tool", fake_call_tool):
        for _ in range(3):
            tool.next_retry_at = 0.0
            result = await reg.dispatch("execute_bash", {"code": "echo hi"})
        blocked = await reg.dispatch("execute_bash", {"code": "echo hi"})

    assert calls == 3
    assert "connection refused" in result["error"]
    assert tool.consecutive_failures == 3
    assert tool.healthy is False
    assert tool.next_retry_at >= t_before + 299
    assert "backoff" in blocked["error"]


@pytest.mark.asyncio
async def test_http_4xx_does_not_trip_backoff():
    reg, tool = _tool("execute_bash")

    async def fake_call_tool(*_a, **_k):
        raise MCPHTTPError("MCP returned HTTP 400", status_code=400)

    with patch.object(registry_module, "call_tool", fake_call_tool):
        result = await reg.dispatch("execute_bash", {"code": "echo hi"})

    assert "HTTP 400" in result["detail"]
    assert tool.healthy is True
    assert tool.consecutive_failures == 0


@pytest.mark.asyncio
async def test_execute_bash_command_alias_reaches_the_server_as_code():
    reg, tool = _tool("execute_bash", _BASH_SCHEMA)
    seen: list[dict] = []

    async def fake_call_tool(_client, _url, name, arguments, _timeout, metadata=None):
        seen.append(arguments)
        return {"content": [{"type": "text", "text": '{"stdout": "ok"}'}]}

    with patch.object(registry_module, "call_tool", fake_call_tool):
        via_command = await reg.dispatch("execute_bash", {"command": "echo portal"})
        via_code = await reg.dispatch("execute_bash", {"code": "echo portal"})
        both = await reg.dispatch("execute_bash", {"code": "keep", "command": "drop"})

    assert via_command == {"stdout": "ok"}
    assert via_code == {"stdout": "ok"}
    assert both == {"stdout": "ok"}
    assert seen == [
        {"code": "echo portal"},
        {"code": "echo portal"},
        {"code": "keep"},
    ]
    assert tool.consecutive_failures == 0


@pytest.mark.asyncio
async def test_command_alias_is_execute_bash_only():
    reg, tool = _tool(
        "render",
        {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    )
    called = False

    async def fake_call_tool(*_a, **_k):
        nonlocal called
        called = True
        return {"content": [{"type": "text", "text": "{}"}]}

    with patch.object(registry_module, "call_tool", fake_call_tool):
        result = await reg.dispatch("render", {"command": "echo"})

    assert called is False
    assert "unexpected keyword argument" in result["detail"]
    assert tool.consecutive_failures == 0


# The sandbox's live REST manifest (curl :8914/tools, 2026-11-05) names the script `command`;
# its MCP function takes `code`. The registry validates against the manifest, so the test
# must use that shape — the `code`-only fixture above hid a release that rejected every call.
_LIVE_BASH_MANIFEST = {
    "type": "object",
    "properties": {
        "command": {"type": "string"},
        "timeout": {"type": "integer"},
        "session_id": {"type": "string"},
    },
    "required": ["command"],
}


@pytest.mark.asyncio
async def test_execute_bash_against_the_live_manifest_schema_reaches_the_server_as_code():
    reg, tool = _tool("execute_bash", _LIVE_BASH_MANIFEST)
    seen: list[dict] = []

    async def fake_call_tool(_client, _url, name, arguments, _timeout, metadata=None):
        seen.append(arguments)
        return {"content": [{"type": "text", "text": '{"stdout": "ok"}'}]}

    with patch.object(registry_module, "call_tool", fake_call_tool):
        via_command = await reg.dispatch("execute_bash", {"command": "echo portal"})
        via_code = await reg.dispatch("execute_bash", {"code": "echo portal", "timeout": 5})
        unknown = await reg.dispatch("execute_bash", {"command": "x", "shell": "zsh"})

    assert via_command == {"stdout": "ok"}
    assert via_code == {"stdout": "ok"}
    assert "rejected the arguments" in unknown["error"]
    assert seen == [{"code": "echo portal"}, {"code": "echo portal", "timeout": 5}]
    assert tool.consecutive_failures == 0
