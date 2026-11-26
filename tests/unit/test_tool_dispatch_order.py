"""A hop's tool calls run one at a time, in the order the model emitted them
(operator 2026-10-18): batched dependent calls (remember then recall) raced in parallel."""

from __future__ import annotations

import asyncio

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
