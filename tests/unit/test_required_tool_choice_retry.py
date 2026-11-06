"""tool_choice="required" is enforced by the pipeline, not the engine.

Ollama cannot express "required" on /api/chat (ollama_native._tools_for_choice drops
it), and oMLX 0.7.2 only special-cases "none" — measured live 2026-11-05: required
tool=execute_python exposed 1 tool, ollama-general answered from the RAG excerpt with
0 tool calls on the first try. So the tool loop holds the first completion, and when
it answers with no tool call, drops it and asks once for the call (same messages and
tools). The retry is engine-agnostic: an engine that honours required never violates
it, so oMLX behaviour is unchanged in practice.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import streaming
from portal.platform.inference.router import trace as trace_mod
from portal.platform.inference.router.tool_repeat import (
    GROUNDING_REQUEST,
    REQUIRED_TOOL_REQUEST,
    UNGROUNDED_NOTICE,
)

PLAIN = "test-plain-ws"
TOOLS = [{"type": "function", "function": {"name": "run_sql", "parameters": {}}}]


# --- the streaming (production) tool loop --------------------------------------


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


def _answer(text: str) -> _Resp:
    chunk = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _call() -> _Resp:
    call = {"index": 0, "id": "c", "function": {"name": "run_sql", "arguments": '{"q":"select 1"}'}}
    chunk = {"choices": [{"delta": {"tool_calls": [call]}, "finish_reason": "tool_calls"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _text(out: bytes) -> str:
    parts = []
    for line in out.decode().splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            for choice in json.loads(line[6:]).get("choices") or []:
                parts.append((choice.get("delta") or {}).get("content") or "")
    return "".join(parts)


def _drive(monkeypatch, body: dict, outcomes: list[_Resp], ws_config: dict | None = None):
    monkeypatch.setitem(streaming.WORKSPACES, PLAIN, ws_config or {})
    bodies: list[dict] = []
    executed: list[str] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            bodies.append({"tools": json.get("tools"), "messages": list(json["messages"])})
            return _Stream(outcomes.pop(0))

    async def fake_dispatch(tc, *_a, **_k):
        executed.append(tc["function"]["name"])
        return {"role": "tool", "tool_call_id": tc.get("id"), "name": "run_sql", "content": "42"}

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "ollama")
    monkeypatch.setattr(streaming, "_dispatch_tool_call", fake_dispatch)

    async def run() -> bytes:
        out = b""
        async for chunk in streaming._tool_loop_frames(
            "http://ollama.test/v1/chat/completions", body, PLAIN, "m", "", {"run_sql"}
        ):
            out += chunk
        return out

    return asyncio.run(run()), bodies, executed


def _required_body() -> dict:
    return {
        "messages": [{"role": "user", "content": "how many?"}],
        "model": "m",
        "tools": TOOLS,
        "tool_choice": "required",
    }


def test_an_answer_with_no_call_is_replaced_by_one_call_first_retry(monkeypatch) -> None:
    out, bodies, executed = _drive(
        monkeypatch, _required_body(), [_answer("it is 12"), _call(), _answer("it is 42")]
    )

    assert "it is 42" in _text(out) and "it is 12" not in _text(
        out
    )  # the call-less answer never went out
    assert executed == ["run_sql"] and len(bodies) == 3
    assert (
        bodies[1]["messages"][-1] == REQUIRED_TOOL_REQUEST and bodies[1]["tools"]
    )  # same messages + the ask, tools still offered


def test_still_no_call_after_the_retry_is_delivered_without_another_one(monkeypatch) -> None:
    out, bodies, executed = _drive(
        monkeypatch, _required_body(), [_answer("it is 12"), _answer("still 12")]
    )

    assert "still 12" in _text(out) and "it is 12" not in _text(out)
    assert UNGROUNDED_NOTICE.strip() not in _text(out)  # the notice is require_tool-only
    assert executed == [] and len(bodies) == 2  # exactly one retry, never a loop


def test_a_first_completion_that_calls_a_tool_is_untouched(monkeypatch) -> None:
    out, bodies, executed = _drive(monkeypatch, _required_body(), [_call(), _answer("it is 42")])

    assert "it is 42" in _text(out) and executed == ["run_sql"]
    assert len(bodies) == 2 and all(
        REQUIRED_TOOL_REQUEST not in b["messages"] for b in bodies
    )  # an engine that honours required is never retried


def test_an_auto_request_is_untouched(monkeypatch) -> None:
    body = {**_required_body(), "tool_choice": "auto"}
    out, bodies, _ = _drive(monkeypatch, body, [_answer("hello")])

    assert "hello" in _text(out) and len(bodies) == 1


def test_the_retry_is_recorded_in_the_turn_trace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(trace_mod, "ENABLED", True)
    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path))
    trace_mod.start_trace("p5-required01")
    _drive(monkeypatch, _required_body(), [_answer("it is 12"), _answer("still 12")])
    trace_mod.finalize_trace()

    record = trace_mod.read_trace("p5-required01")
    assert record is not None and record["required_tool_retried"] is True


def test_a_require_tool_workspace_keeps_the_grounding_ask(monkeypatch) -> None:
    """The workspace flag predates tool_choice=required and keeps its own ask and notice."""
    body = {**_required_body(), "tool_choice": None}
    out, bodies, executed = _drive(
        monkeypatch,
        body,
        [_answer("it is 12"), _answer("still 12")],
        ws_config={"require_tool_before_answer": True},
    )

    assert "still 12" in _text(out) and UNGROUNDED_NOTICE.strip() in _text(out)
    assert bodies[1]["messages"][-1] == GROUNDING_REQUEST and executed == [] and len(bodies) == 2


# --- the non-streaming (failover) path ------------------------------------------


class _NSClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.bodies: list[dict] = []

    async def post(self, url, json, timeout):  # noqa: A002
        self.bodies.append(dict(json))
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def _reply(content: str = "", call: bool = False) -> httpx.Response:
    msg: dict = {"role": "assistant", "content": content}
    if call:
        msg["tool_calls"] = [
            {"id": "c", "type": "function", "function": {"name": "run_sql", "arguments": "{}"}}
        ]
    return httpx.Response(200, json={"choices": [{"message": msg}]})


@pytest.fixture
def ns_plain(monkeypatch: pytest.MonkeyPatch):
    from portal.platform.inference import tool_registry as registry_mod

    monkeypatch.setitem(ns.WORKSPACES, PLAIN, {"model_hint": "m"})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(ns, "_resolve_persona_tools", lambda *_a: ["run_sql"])
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
        return {"role": "tool", "tool_call_id": tc.get("id"), "content": "42"}

    monkeypatch.setattr(ns, "_dispatch_tool_call", dispatch)
    backend = SimpleNamespace(
        id="b", type="ollama", chat_url="http://b/v1/chat/completions", models=["m"],
        resolve_model=lambda h: h,
    )  # fmt: skip
    return backend, executed


def _ns_body() -> dict:
    return {"messages": [], "tools": TOOLS, "tool_choice": "required", "model": "m"}


@pytest.mark.anyio
async def test_failover_retries_a_call_less_answer_once(monkeypatch, ns_plain) -> None:
    backend, executed = ns_plain
    client = _NSClient([_reply("it is 12"), _reply(call=True), _reply("it is 42")])
    monkeypatch.setattr(ns, "_http_client", client)

    result = await ns._try_non_streaming(backend, _ns_body(), PLAIN, 0.0, max_hops=20)

    content = json.loads(result.body)["choices"][0]["message"]["content"]
    assert content == "it is 42" and executed == ["c"]
    assert client.bodies[1]["messages"][-1] == REQUIRED_TOOL_REQUEST and client.bodies[1]["tools"]


@pytest.mark.anyio
async def test_failover_delivers_a_still_call_less_answer_without_another_retry(
    monkeypatch, ns_plain
) -> None:
    backend, executed = ns_plain
    client = _NSClient([_reply("it is 12"), _reply("still 12")])
    monkeypatch.setattr(ns, "_http_client", client)

    result = await ns._try_non_streaming(backend, _ns_body(), PLAIN, 0.0, max_hops=20)

    content = json.loads(result.body)["choices"][0]["message"]["content"]
    assert content == "still 12" and executed == [] and len(client.bodies) == 2


@pytest.mark.anyio
async def test_failover_untouched_when_the_first_completion_calls_a_tool(
    monkeypatch, ns_plain
) -> None:
    backend, executed = ns_plain
    client = _NSClient([_reply(call=True), _reply("it is 42")])
    monkeypatch.setattr(ns, "_http_client", client)

    result = await ns._try_non_streaming(backend, _ns_body(), PLAIN, 0.0, max_hops=20)

    content = json.loads(result.body)["choices"][0]["message"]["content"]
    assert content == "it is 42" and executed == ["c"] and len(client.bodies) == 2


def test_no_tool_call_retry_spends_exactly_once() -> None:
    """One budget per turn, whichever ask it buys; require_tool keeps GROUNDING_REQUEST."""
    guard = ns.ToolRepeatGuard()
    assert ns.no_tool_call_retry(guard, False) is REQUIRED_TOOL_REQUEST
    assert ns.no_tool_call_retry(guard, False) is None
    grounded = ns.ToolRepeatGuard()
    assert ns.no_tool_call_retry(grounded, True) is GROUNDING_REQUEST
    assert ns.no_tool_call_retry(grounded, True) is None
