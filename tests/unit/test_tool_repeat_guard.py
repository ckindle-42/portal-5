"""A model that re-issues a tool call it already made is answered from the earlier result, and a
third identical request ends the tool loop with a final turn that has no tools. Measured on
Qwen3.8 (compliance seat, 2026-10-16): one call repeated up to 19 times until the hop limit."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import streaming
from portal.platform.inference.router.tool_repeat import REPEAT_NOTE, ToolRepeatGuard, call_key


def _call(name: str = "lookup", args: object = None, cid: str = "c1") -> dict:
    raw = json.dumps({"req": "CIP-013-2"} if args is None else args)
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": raw}}


def test_a_repeat_is_answered_from_the_earlier_result_with_the_note() -> None:
    guard = ToolRepeatGuard()
    assert guard.seen(_call()) is False
    guard.remember(_call(), {"role": "tool", "content": "RESULT"})

    assert guard.seen(_call(cid="c2")) is True
    msg = guard.repeat_result(_call(cid="c2"))
    assert msg["role"] == "tool" and msg["tool_call_id"] == "c2"
    assert msg["content"].startswith("RESULT") and REPEAT_NOTE in msg["content"]
    assert guard.force_synthesis is False


def test_the_third_identical_request_forces_a_final_turn_without_tools() -> None:
    guard = ToolRepeatGuard()
    guard.seen(_call())
    guard.remember(_call(), {"content": "R"})
    guard.seen(_call())
    assert guard.force_synthesis is False
    guard.seen(_call())
    assert guard.force_synthesis is True and guard.suppressed == 2


def test_different_arguments_are_a_new_call_and_key_order_is_not() -> None:
    guard = ToolRepeatGuard()
    guard.seen(_call(args={"a": 1, "b": 2}))
    guard.remember(_call(args={"a": 1, "b": 2}), {"content": "R"})

    assert guard.seen(_call(args={"a": 1, "b": 3})) is False
    assert guard.seen(_call(args={"b": 2, "a": 1})) is True  # same call, reordered keys
    assert call_key(_call(args={"a": 1})) == call_key(_call(args={"a": 1}))
    assert guard.seen(_call(name="other", args={"a": 1, "b": 2})) is False


def test_a_new_turn_starts_with_nothing_remembered() -> None:
    first = ToolRepeatGuard()
    first.seen(_call())
    first.remember(_call(), {"content": "R"})
    assert ToolRepeatGuard().seen(_call()) is False


class _Resp:
    def __init__(self, lines: list[str]) -> None:
        self.status_code = 200
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _Stream:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _Resp:
        return self._resp

    async def __aexit__(self, *exc) -> None:
        return None


def _tool_frame(args: str = '{"req":"CIP-013-2"}') -> _Resp:
    call = {"index": 0, "id": "c", "function": {"name": "lookup", "arguments": args}}
    chunk = {"choices": [{"delta": {"tool_calls": [call]}, "finish_reason": "tool_calls"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _answer_frame(text: str) -> _Resp:
    chunk = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def test_the_streaming_loop_runs_a_stuck_call_once_and_ends_with_a_toolless_turn(
    monkeypatch,
) -> None:
    outcomes = [_tool_frame(), _tool_frame(), _tool_frame(), _answer_frame("the answer")]
    bodies: list[dict] = []
    executed: list[str] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            bodies.append({"tools": json.get("tools"), "messages": list(json["messages"])})
            return _Stream(outcomes.pop(0))

    async def fake_dispatch(tc, *_a, **_k):
        executed.append(tc["function"]["name"])
        return {"role": "tool", "tool_call_id": tc.get("id"), "name": "lookup", "content": "RESULT"}

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "omlx")
    monkeypatch.setattr(streaming, "_dispatch_tool_call", fake_dispatch)

    async def run() -> bytes:
        out = b""
        async for chunk in streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            {
                "messages": [{"role": "user", "content": "hi"}],
                "model": "m",
                "tools": [{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
            },
            "auto-daily",
            "m",
            "",
            {"lookup"},
        ):
            out += chunk
        return out

    out = asyncio.run(run())

    assert b"the answer" in out
    assert executed == ["lookup"]  # the stuck call ran once; the two repeats came from the cache
    assert len(bodies) == 4
    assert bodies[2]["tools"] and bodies[3]["tools"] is None  # tools withheld after the 3rd request
    tool_msgs = [m for m in bodies[3]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 3 and REPEAT_NOTE in tool_msgs[1]["content"]


def test_the_streaming_loop_still_runs_a_call_with_new_arguments(monkeypatch) -> None:
    outcomes = [_tool_frame('{"req":"A"}'), _tool_frame('{"req":"B"}'), _answer_frame("done")]
    executed: list[str] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            return _Stream(outcomes.pop(0))

    async def fake_dispatch(tc, *_a, **_k):
        executed.append(tc["function"]["arguments"])
        return {"role": "tool", "tool_call_id": tc.get("id"), "name": "lookup", "content": "R"}

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "omlx")
    monkeypatch.setattr(streaming, "_dispatch_tool_call", fake_dispatch)

    async def run() -> bytes:
        out = b""
        async for chunk in streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            {
                "messages": [{"role": "user", "content": "hi"}],
                "model": "m",
                "tools": [{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
            },
            "auto-daily",
            "m",
            "",
            {"lookup"},
        ):
            out += chunk
        return out

    assert b"done" in asyncio.run(run())
    assert executed == ['{"req":"A"}', '{"req":"B"}']


# ── the non-streaming (failover) loop ───────────────────────────────


class _NSClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.bodies: list[dict] = []

    async def post(self, url, json, timeout):  # noqa: A002
        self.bodies.append(dict(json))
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def _ns_tool_reply() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [_call()]}}]
        },
    )


@pytest.mark.anyio
async def test_the_failover_loop_applies_the_same_guard(monkeypatch) -> None:
    from types import SimpleNamespace

    from portal.platform.inference import tool_registry as registry_mod

    ws = "test-repeat-ws"
    monkeypatch.setitem(ns.WORKSPACES, ws, {"model_hint": "m"})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(ns, "_resolve_persona_tools", lambda *_a: ["lookup"])
    monkeypatch.setattr(ns, "apply_eval_scope", lambda _b, tools: tools)

    async def refresh() -> None:
        return None

    monkeypatch.setattr(registry_mod.tool_registry, "refresh", refresh)
    monkeypatch.setattr(
        registry_mod.tool_registry,
        "get_openai_tools",
        lambda names: [
            {"type": "function", "function": {"name": n, "parameters": {}}} for n in names
        ],
    )
    executed: list[str] = []

    async def dispatch(tc, *_a, **_k):
        executed.append(tc["id"])
        return {"role": "tool", "tool_call_id": tc.get("id"), "content": "RESULT"}

    monkeypatch.setattr(ns, "_dispatch_tool_call", dispatch)
    final = httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    )
    client = _NSClient([_ns_tool_reply(), _ns_tool_reply(), _ns_tool_reply(), final])
    monkeypatch.setattr(ns, "_http_client", client)

    backend = SimpleNamespace(
        id="b",
        type="ollama",
        chat_url="http://b/v1/chat/completions",
        models=["m"],
        resolve_model=lambda h: h,
    )
    result = await ns._try_non_streaming(backend, {"messages": []}, ws, 0.0, max_hops=20)

    assert json.loads(result.body)["choices"][0]["message"]["content"] == "ok"
    assert len(executed) == 1  # the same call is run once for the whole turn
    assert client.bodies[3]["tools"] is None  # the turn ends with a toolless synthesis
