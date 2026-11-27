"""A hop's tool calls run one at a time, in the order the model emitted them
(operator 2026-10-18): batched dependent calls (remember then recall) raced in parallel."""

from __future__ import annotations

import asyncio
import json

import pytest

from portal.platform.inference.router import streaming


def _call(name: str, i: int) -> dict:
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": "{}"}}


@pytest.mark.anyio
async def test_each_call_finishes_before_the_next_starts(monkeypatch) -> None:
    events: list[str] = []

    async def fake_dispatch(tc, _tools, _ws, _persona, _rid):
        name = tc["function"]["name"]
        events.append(f"start:{name}")
        await asyncio.sleep(0.01)
        events.append(f"end:{name}")
        return {"role": "tool", "tool_call_id": tc["id"], "content": "{}"}

    monkeypatch.setattr(streaming, "_dispatch_tool_call", fake_dispatch)
    calls = [_call("remember", 0), _call("recall", 1), _call("execute_python", 2)]
    _msg, results = await streaming._dispatch_hop_tool_calls(
        calls, {"remember", "recall", "execute_python"}, "tools-specialist", "", "rid", 1, 20
    )
    assert events == [
        "start:remember",
        "end:remember",
        "start:recall",
        "end:recall",
        "start:execute_python",
        "end:execute_python",
    ]
    assert [r["tool_call_id"] for r in results] == ["c0", "c1", "c2"]


@pytest.mark.asyncio
async def test_pipeline_forwards_workspace_on_native_tool_dispatch(monkeypatch) -> None:
    from portal.platform.inference import tool_registry
    from portal.platform.inference.router import tools as router_tools

    recorded: list[tuple[str, str]] = []

    async def dispatch(_name, _arguments, request_id="", workspace_id=""):
        recorded.append((request_id, workspace_id))
        return {"success": True}

    monkeypatch.setattr(tool_registry.tool_registry, "dispatch", dispatch)
    call = {
        "id": "call-1",
        "function": {"name": "execute_bash", "arguments": '{"code":"true"}'},
    }

    await router_tools._dispatch_tool_call(
        call,
        {"execute_bash"},
        "auto-security::purpleteam-exec",
        "",
        "request-1",
    )

    assert recorded == [("request-1", "auto-security::purpleteam-exec")]


def _completed(record: dict) -> list[dict]:
    return [span for span in record["spans"] if span["name"] == "tool.completed"]


@pytest.mark.asyncio
async def test_dispatch_traces_structured_mcp_results_without_memory_text(monkeypatch, tmp_path):
    from portal.platform.inference import tool_registry
    from portal.platform.inference.router import tools as router_tools
    from portal.platform.inference.router import trace

    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path))
    payload = {
        "query": "QAT label",
        "num_results": 2,
        "memories": [
            {"id": "memory-1", "text": "private memory one"},
            {"id": "memory-2", "text": "private memory two"},
        ],
    }

    async def dispatch(_name, _arguments, request_id="", workspace_id=""):
        del request_id, workspace_id
        return payload

    monkeypatch.setattr(tool_registry.tool_registry, "dispatch", dispatch)
    trace.start_trace("p5-structuredresult")
    try:
        tool_message = await router_tools._dispatch_tool_call(
            {"id": "call-memory", "function": {"name": "recall", "arguments": "{}"}},
            {"recall"},
            "auto-daily",
            "daily",
            "request-memory",
        )
        trace.finalize_trace()
        record = trace.read_trace("p5-structuredresult")
    finally:
        trace._current.set(None)

    assert json.loads(tool_message["content"]) == payload
    span = _completed(record)[0]
    assert span["stdout_head"] == ""
    assert span["result_shape"] == {
        "keys": ["memories", "num_results", "query"],
        "num_results": 2,
        "memories_count": 2,
        "memory_ids": ["memory-1", "memory-2"],
    }
    assert "private memory" not in str(record)


async def test_dispatch_records_a_bounded_redacted_tool_result(monkeypatch, tmp_path):
    from portal.platform.inference import tool_registry
    from portal.platform.inference.router import tools as router_tools
    from portal.platform.inference.router import trace

    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path))

    async def dispatch(_name, _arguments, request_id="", workspace_id=""):
        del request_id, workspace_id
        return {
            "success": True,
            "stdout": "UAT_PYTHON_73\npassword=hunter2\n" + ("x" * 600),
            "stderr": "token=abc",
            "api_key": "sekrit",
            "exit_code": 0,
        }

    monkeypatch.setattr(tool_registry.tool_registry, "dispatch", dispatch)
    trace.start_trace("p5-toolresult1")
    try:
        await router_tools._dispatch_tool_call(
            {"id": "call-1", "function": {"name": "execute_python", "arguments": "{}"}},
            {"execute_python"},
            "auto-coding",
            "coding",
            "request-1",
        )
        trace.finalize_trace()
        record = trace.read_trace("p5-toolresult1")
    finally:
        trace._current.set(None)

    assert record is not None
    assert record["tool_calls"] == 1
    span = _completed(record)[0]
    assert span["tool"] == "execute_python"
    assert span["outcome"] == "ok"
    assert span["success"] is True
    assert span["error_type"] == ""
    assert span["stdout_head"].startswith("UAT_PYTHON_73\npassword=<redacted>\n")
    assert span["stderr_head"] == "token=<redacted>"
    assert span["stdout_truncated"] is True
    assert len(span["stdout_head"]) == trace.TOOL_RESULT_HEAD_CHARS
    dumped = str(record)
    assert "hunter2" not in dumped and "sekrit" not in dumped and "abc" not in dumped


async def test_dispatch_records_sandbox_error_type_without_the_error_text(monkeypatch, tmp_path):
    from portal.platform.inference import tool_registry
    from portal.platform.inference.router import tools as router_tools
    from portal.platform.inference.router import trace

    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path))

    async def dispatch(_name, _arguments, request_id="", workspace_id=""):
        del request_id, workspace_id
        return {
            "success": False,
            "error_type": "nonzero_exit",
            "error": "secret=do-not-store",
            "stdout": "",
            "stderr": "boom",
            "exit_code": 1,
        }

    monkeypatch.setattr(tool_registry.tool_registry, "dispatch", dispatch)
    trace.start_trace("p5-toolresult2")
    try:
        await router_tools._dispatch_tool_call(
            {"id": "call-2", "function": {"name": "execute_bash", "arguments": "{}"}},
            {"execute_bash"},
            "auto-coding",
            "",
            "request-2",
        )
        await router_tools._dispatch_tool_call(
            {"id": "call-3", "function": {"name": "execute_bash", "arguments": "{"}},
            {"execute_bash"},
            "auto-coding",
            "",
            "request-2",
        )
        trace.finalize_trace()
        record = trace.read_trace("p5-toolresult2")
    finally:
        trace._current.set(None)

    assert record is not None
    spans = _completed(record)
    assert [(span["outcome"], span["success"], span["error_type"]) for span in spans] == [
        ("error", False, "nonzero_exit"),
        ("invalid_arguments", False, "tool_arg_parse"),
    ]
    assert "do-not-store" not in str(record)
    assert spans[0]["error_head"] == "secret=<redacted>"
    assert spans[0]["stderr_head"] == "boom"
    assert spans[1]["error_head"].startswith("Invalid JSON arguments:")
    assert spans[1]["stdout_head"] == "" and spans[1]["stderr_head"] == ""


def test_tool_error_head_is_capped_and_redacted() -> None:
    from portal.platform.inference.router import trace

    fields = trace.bounded_tool_result(
        {"success": False, "error": "password=hunter2 " + ("e" * 600)}
    )
    assert fields["error_type"] == "tool_error"
    assert fields["error_head"].startswith("password=<redacted> ")
    assert "hunter2" not in fields["error_head"]
    assert len(fields["error_head"]) == trace.TOOL_RESULT_HEAD_CHARS
    assert fields["error_truncated"] is True
    assert fields["stdout_head"] == "" and fields["stderr_head"] == ""


@pytest.mark.asyncio
async def test_dispatch_applies_workspace_tool_model_default_when_omitted_or_default(monkeypatch):
    from portal.platform.inference import tool_registry
    from portal.platform.inference.router import tools as router_tools

    seen: list[dict[str, object]] = []

    async def dispatch(_name, arguments, request_id="", workspace_id=""):
        del request_id, workspace_id
        seen.append(dict(arguments))
        return {"ok": True}

    monkeypatch.setattr(tool_registry.tool_registry, "dispatch", dispatch)
    for args in (
        '{"question":"q","ref":"CIP-007-6 R2.2"}',
        '{"question":"q","ref":"CIP-007-6 R2.2","model":""}',
        '{"question":"q","ref":"CIP-007-6 R2.2","model":"default"}',
        '{"question":"q","ref":"CIP-007-6 R2.2","model":"compliance-mapping"}',
    ):
        await router_tools._dispatch_tool_call(
            {"id": "c1", "function": {"name": "compliance_ask", "arguments": args}},
            {"compliance_ask"},
            "auto-compliance",
            "",
            "rid",
        )

    assert [item["model"] for item in seen] == [
        "compliance-council-qwen38",
        "compliance-council-qwen38",
        "compliance-council-qwen38",
        "compliance-mapping",
    ]
