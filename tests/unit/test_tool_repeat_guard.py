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
from portal.platform.inference.router.tool_repeat import (
    FINAL_ANSWER_REQUEST,
    REPEAT_NOTE,
    ToolRepeatGuard,
    call_key,
)


def _call(name: str = "kb_search", args: object = None, cid: str = "c1") -> dict:
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


def test_a_rerun_after_a_state_change_is_not_a_repeat() -> None:
    """edit -> run the tests -> edit -> run the tests: the second `pytest` has the same name and
    arguments as the first and a different answer, so it must run (and so must the edit)."""
    guard = ToolRepeatGuard()
    pytest_call = _call("execute_bash", {"command": "pytest -q"}, "1")
    edit = _call("execute_bash", {"command": "sed -i 's/a/b/' mod.py"}, "2")

    assert guard.seen(pytest_call) is False
    guard.remember(pytest_call, {"content": "1 failed"})
    assert guard.seen(edit) is False
    guard.remember(edit, {"content": ""})
    assert guard.seen(_call("execute_bash", {"command": "pytest -q"}, "3")) is False
    assert guard.suppressed == 0 and guard.force_synthesis is False


def test_an_identical_exec_call_is_never_answered_from_the_cache() -> None:
    guard = ToolRepeatGuard()
    run = _call("execute_python", {"code": "print(1)"}, "1")
    for _ in range(4):
        assert guard.seen(run) is False  # it may append to a file; only read tools are cached
        guard.remember(run, {"content": "1"})
    assert guard.force_synthesis is False


def test_a_write_clears_the_cache_of_reads_made_before_it() -> None:
    guard = ToolRepeatGuard()
    read = _call("kb_search", {"query": "x"}, "1")
    guard.seen(read)
    guard.remember(read, {"content": "old hit"})
    assert guard.seen(_call("kb_search", {"query": "x"}, "2")) is True  # a plain repeat

    guard.seen(_call("remember", {"text": "fact"}, "3"))  # a write runs
    assert guard.seen(_call("kb_search", {"query": "x"}, "4")) is False  # the read runs again


def test_the_reading_surface_is_cached_and_the_compliance_writers_are_not() -> None:
    from portal.platform.inference.router.tool_repeat import is_read_only

    for name in (
        "nerc_cip_requirement",
        "compliance_read",
        "kb_search",
        "run_sql",
        "profile_table",
    ):
        assert is_read_only(name), name
    for name in (
        "execute_bash",
        "create_excel",
        "remember",
        "compliance_note",
        "attach_source",
        "mystery",
    ):
        assert not is_read_only(name), name


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
    call = {"index": 0, "id": "c", "function": {"name": "kb_search", "arguments": args}}
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
        return {
            "role": "tool",
            "tool_call_id": tc.get("id"),
            "name": "kb_search",
            "content": "RESULT",
        }

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
                "tools": [
                    {"type": "function", "function": {"name": "kb_search", "parameters": {}}}
                ],
            },
            "auto-daily",
            "m",
            "",
            {"kb_search"},
        ):
            out += chunk
        return out

    out = asyncio.run(run())

    assert b"the answer" in out
    assert executed == ["kb_search"]  # the stuck call ran once; the two repeats came from the cache
    assert len(bodies) == 4
    assert bodies[2]["tools"] and bodies[3]["tools"] is None  # tools withheld after the 3rd request
    tool_msgs = [m for m in bodies[3]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 3 and REPEAT_NOTE in tool_msgs[1]["content"]
    assert bodies[3]["messages"][-1] == FINAL_ANSWER_REQUEST  # told to answer from what it has


def test_a_toolless_final_turn_never_delivers_call_markup(monkeypatch) -> None:
    """Live 2026-10-16: with the tools withheld the model wrote its call out as text and the
    client received `<tool_call><function=...>` as the answer."""
    markup = (
        "<tool_call>\n<function=lookup>\n<parameter=req>\nCIP-013-2\n</parameter>\n"
        "</function>\n</tool_call>"
    )
    outcomes = [_tool_frame(), _tool_frame(), _tool_frame(), _answer_frame(markup)]

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            return _Stream(outcomes.pop(0))

    async def fake_dispatch(tc, *_a, **_k):
        return {"role": "tool", "tool_call_id": tc.get("id"), "name": "kb_search", "content": "R"}

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
                "tools": [
                    {"type": "function", "function": {"name": "kb_search", "parameters": {}}}
                ],
            },
            "auto-daily",
            "m",
            "",
            {"kb_search"},
        ):
            out += chunk
        return out

    out = asyncio.run(run())

    assert b"<tool_call>" not in out and b"<function=" not in out


def test_the_streaming_loop_still_runs_a_call_with_new_arguments(monkeypatch) -> None:
    outcomes = [_tool_frame('{"req":"A"}'), _tool_frame('{"req":"B"}'), _answer_frame("done")]
    executed: list[str] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            return _Stream(outcomes.pop(0))

    async def fake_dispatch(tc, *_a, **_k):
        executed.append(tc["function"]["arguments"])
        return {"role": "tool", "tool_call_id": tc.get("id"), "name": "kb_search", "content": "R"}

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
                "tools": [
                    {"type": "function", "function": {"name": "kb_search", "parameters": {}}}
                ],
            },
            "auto-daily",
            "m",
            "",
            {"kb_search"},
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
    monkeypatch.setattr(ns, "_resolve_persona_tools", lambda *_a: ["kb_search"])
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
    assert client.bodies[3]["messages"][-1] == FINAL_ANSWER_REQUEST
