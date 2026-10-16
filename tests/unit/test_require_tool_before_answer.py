"""A workspace flagged `require_tool_before_answer` does not deliver an answer given from nothing:
the pipeline asks once for a grounded one, then delivers with a notice. Measured on auto-data
(Qwen3.6): about 1 turn in 10 answered with no query, often with a fabricated number."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import streaming
from portal.platform.inference.router.tool_repeat import GROUNDING_REQUEST, UNGROUNDED_NOTICE

FLAGGED = "test-require-tool-ws"
PLAIN = "test-plain-ws"
TOOLS = [{"type": "function", "function": {"name": "run_sql", "parameters": {}}}]


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
    """The answer text a client would assemble from the SSE frames."""
    parts = []
    for line in out.decode().splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            for choice in json.loads(line[6:]).get("choices") or []:
                parts.append((choice.get("delta") or {}).get("content") or "")
    return "".join(parts)


def _drive(monkeypatch, workspace: str, outcomes: list[_Resp]):
    monkeypatch.setitem(streaming.WORKSPACES, FLAGGED, {"require_tool_before_answer": True})
    monkeypatch.setitem(streaming.WORKSPACES, PLAIN, {})
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
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "omlx")
    monkeypatch.setattr(streaming, "_dispatch_tool_call", fake_dispatch)

    async def run() -> bytes:
        out = b""
        async for chunk in streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            {"messages": [{"role": "user", "content": "how many?"}], "model": "m", "tools": TOOLS},
            workspace,
            "m",
            "",
            {"run_sql"},
        ):
            out += chunk
        return out

    return asyncio.run(run()), bodies, executed


def test_an_answer_with_no_tool_call_is_replaced_by_one_grounded_retry(monkeypatch) -> None:
    out, bodies, executed = _drive(
        monkeypatch, FLAGGED, [_answer("it is 12"), _call(), _answer("it is 42")]
    )

    assert "it is 42" in _text(out) and "it is 12" not in _text(
        out
    )  # the ungrounded answer never went out
    assert executed == ["run_sql"] and len(bodies) == 3
    assert (
        bodies[1]["messages"][-1] == GROUNDING_REQUEST and bodies[1]["tools"]
    )  # tools still offered
    assert UNGROUNDED_NOTICE.strip() not in _text(out)  # a query ran, so no notice


def test_still_ungrounded_after_the_retry_is_delivered_with_a_notice(monkeypatch) -> None:
    out, bodies, executed = _drive(monkeypatch, FLAGGED, [_answer("it is 12"), _answer("still 12")])

    assert "still 12" in _text(out) and "it is 12" not in _text(out)
    assert UNGROUNDED_NOTICE.strip() in _text(out)
    assert executed == [] and len(bodies) == 2  # exactly one retry, never a loop


def test_a_turn_that_calls_a_tool_is_untouched(monkeypatch) -> None:
    out, bodies, executed = _drive(monkeypatch, FLAGGED, [_call(), _answer("it is 42")])

    assert "it is 42" in _text(out) and UNGROUNDED_NOTICE.strip() not in _text(out)
    assert executed == ["run_sql"] and len(bodies) == 2
    assert GROUNDING_REQUEST not in bodies[1]["messages"]


def test_an_unflagged_workspace_is_untouched(monkeypatch) -> None:
    out, bodies, _ = _drive(monkeypatch, PLAIN, [_answer("hello")])

    assert "hello" in _text(out) and UNGROUNDED_NOTICE.strip() not in _text(out)
    assert len(bodies) == 1


# ── the non-streaming (failover) path ───────────────────────────────


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
def ns_flagged(monkeypatch: pytest.MonkeyPatch):
    from portal.platform.inference import tool_registry as registry_mod

    monkeypatch.setitem(
        ns.WORKSPACES, FLAGGED, {"model_hint": "m", "require_tool_before_answer": True}
    )
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


@pytest.mark.anyio
async def test_failover_retries_once_and_a_recovered_call_runs(monkeypatch, ns_flagged) -> None:
    backend, executed = ns_flagged
    client = _NSClient([_reply("it is 12"), _reply(call=True), _reply("it is 42")])
    monkeypatch.setattr(ns, "_http_client", client)

    result = await ns._try_non_streaming(backend, {"messages": []}, FLAGGED, 0.0, max_hops=20)

    content = json.loads(result.body)["choices"][0]["message"]["content"]
    assert content == "it is 42" and executed == ["c"]
    assert client.bodies[1]["messages"][-1] == GROUNDING_REQUEST and client.bodies[1]["tools"]


@pytest.mark.anyio
async def test_failover_delivers_a_still_ungrounded_answer_with_the_notice(
    monkeypatch, ns_flagged
) -> None:
    backend, executed = ns_flagged
    client = _NSClient([_reply("it is 12"), _reply("still 12")])
    monkeypatch.setattr(ns, "_http_client", client)

    result = await ns._try_non_streaming(backend, {"messages": []}, FLAGGED, 0.0, max_hops=20)

    content = json.loads(result.body)["choices"][0]["message"]["content"]
    assert content == "still 12" + UNGROUNDED_NOTICE and executed == [] and len(client.bodies) == 2
