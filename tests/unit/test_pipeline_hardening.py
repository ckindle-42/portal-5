"""Regression tests for the pipeline hardening pass (2026-09-25).

Each test pins one defect that was reproduced live against the running stack:
list-form system content 500s, reasoning printed as the answer, frames after
[DONE], fallback appending a second answer, the same (engine, model) retried,
wrong-model substitution, opaque 502s, content:null tool replies, Anthropic
x-api-key 401s and dropped tool_use / tool_result blocks, the tool circuit
breaker tripping on bad arguments, and OWUI task prompts stored as memories.
"""

from __future__ import annotations

import json
import typing
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

import portal.platform.inference.router.non_streaming as ns
import portal.platform.inference.router.streaming as st
from portal.platform.inference.router.anthropic_compat import (
    anthropic_to_openai_body,
    openai_stream_to_anthropic_sse,
)
from portal.platform.inference.router.context_inject import (
    _inject_context_block,
    _salient_user_text,
)
from portal.platform.inference.router.preinject import (
    _inject_system_prompt_append,
    append_text_to_content,
)

DONE = b"data: [DONE]\n\n"


@pytest.fixture
def api() -> typing.Iterator[typing.Any]:
    """FastAPI TestClient over the real app with a fake backend registry."""
    from fastapi.testclient import TestClient

    import portal.platform.inference.router.handlers as handlers_mod
    from portal.platform.inference.router_pipe import app
    from tests.unit.test_pipeline import _make_fake_backend

    handlers_mod.registry = _make_fake_backend()
    with TestClient(app) as test_client:
        yield test_client
    handlers_mod.registry = None


def _data(obj: dict[str, typing.Any]) -> str:
    return "data: " + json.dumps(obj, separators=(",", ":"))


def _delta(**delta: typing.Any) -> str:
    return _data({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]})


class _Resp:
    def __init__(self, status: int, lines: list[str], body: bytes = b"") -> None:
        self.status_code = status
        self._lines = lines
        self._body = body

    async def aiter_lines(self) -> typing.AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return self._body


class _Ctx:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _Resp:
        return self._resp

    async def __aexit__(self, *_: typing.Any) -> None:
        return None


@pytest.fixture
def stream_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr(st, "_http_client", client)
    return client


def _serve(client: MagicMock, *responses: _Resp) -> None:
    queue = list(responses)
    client.stream = lambda *_a, **_k: _Ctx(queue.pop(0))


async def _drain(gen: typing.AsyncIterator[bytes]) -> list[bytes]:
    return [c async for c in gen]


def _payloads(chunks: list[bytes]) -> list[dict[str, typing.Any]]:
    out = []
    for c in chunks:
        for line in c.decode().splitlines():
            if line.startswith("data: ") and line[6:] != "[DONE]":
                out.append(json.loads(line[6:]))
    return out


def _content(chunks: list[bytes]) -> str:
    return "".join(
        (ch.get("delta") or {}).get("content") or ""
        for p in _payloads(chunks)
        for ch in p.get("choices") or []
    )


# ── list-form content ────────────────────────────────────────────────


def test_system_append_accepts_list_content() -> None:
    assert append_text_to_content([{"type": "text", "text": "a"}], "b") == [
        {"type": "text", "text": "a"},
        {"type": "text", "text": "b"},
    ]
    assert append_text_to_content(None, "b") == "b"
    body = {"messages": [{"role": "system", "content": [{"type": "text", "text": "terse"}]}]}
    ws = next(iter(st.WORKSPACES))
    st.WORKSPACES[ws] = {**st.WORKSPACES[ws], "system_prompt_append": "\nAPPENDED"}
    try:
        out = _inject_system_prompt_append(ws, body)
    finally:
        st.WORKSPACES[ws].pop("system_prompt_append")
    assert out["messages"][0]["content"][-1] == {"type": "text", "text": "\nAPPENDED"}
    blocked = _inject_context_block(body, "Header:", ["x"])
    assert blocked["messages"][0]["content"][-1]["text"].startswith("Header:")


# ── guarded stream: reasoning display ────────────────────────────────


@pytest.mark.anyio
async def test_reasoning_passes_through_and_content_stays_the_answer(stream_client) -> None:
    _serve(
        stream_client,
        _Resp(
            200,
            [_delta(content="", reasoning="thinking hard"), _delta(content="391"), "data: [DONE]"],
        ),
    )
    chunks = await _drain(st._stream_from_backend_guarded("http://x/v1/chat/completions", {}))
    assert _content(chunks) == "391"
    assert any(
        (c.get("delta") or {}).get("reasoning") for p in _payloads(chunks) for c in p["choices"]
    )
    assert chunks[-1] == DONE


@pytest.mark.anyio
async def test_reasoning_only_turn_is_promoted_before_done(stream_client) -> None:
    usage = _data({"choices": [], "usage": {"completion_tokens": 50}})
    _serve(
        stream_client,
        _Resp(200, [_delta(content="", reasoning="only thoughts"), usage, "data: [DONE]"]),
    )
    chunks = await _drain(st._stream_from_backend_guarded("http://x/v1/chat/completions", {}))
    assert _content(chunks) == "only thoughts"
    assert "empty response" not in _content(chunks)
    assert chunks[-1] == DONE


@pytest.mark.anyio
async def test_spaced_json_content_is_not_reported_empty(stream_client) -> None:
    spaced = "data: " + json.dumps({"choices": [{"delta": {"content": "hi"}}]})  # ": " separators
    usage = _data({"choices": [], "usage": {"completion_tokens": 5}})
    _serve(stream_client, _Resp(200, [spaced, usage, "data: [DONE]"]))
    chunks = await _drain(st._stream_from_backend_guarded("http://x/v1/chat/completions", {}))
    assert "empty response" not in _content(chunks)


@pytest.mark.anyio
async def test_client_tool_call_is_not_reported_empty(stream_client) -> None:
    tc = _delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "f", "arguments": "{}"}}])
    usage = _data({"choices": [], "usage": {"completion_tokens": 9}})
    _serve(stream_client, _Resp(200, [tc, usage, "data: [DONE]"]))
    chunks = await _drain(st._stream_from_backend_guarded("http://x/v1/chat/completions", {}))
    assert "empty response" not in _content(chunks)


@pytest.mark.anyio
async def test_backend_error_chunk_carries_status_and_message(stream_client) -> None:
    _serve(stream_client, _Resp(400, [], b'{"error":{"message":"bad top_k"}}'))
    chunks = await _drain(st._stream_from_backend_guarded("http://x/v1/chat/completions", {}))
    err = _payloads(chunks)[0]
    assert err["status"] == 400 and "bad top_k" in err["error"]


# ── tool loop: [DONE] is last ────────────────────────────────────────


@pytest.mark.anyio
async def test_tool_loop_emits_single_done_after_fallback(stream_client) -> None:
    _serve(
        stream_client,
        _Resp(200, [_delta(content="", reasoning="deep thought"), "data: [DONE]"]),
    )
    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://x/v1/chat/completions", {"messages": []}, "ws", "m", "p", set()
        )
    )
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE
    assert "deep thought" in _content(chunks)
    assert "empty response" not in _content(chunks)


# ── stream fallback policy ───────────────────────────────────────────


def _backend(bid: str, url: str = "http://engine", models: list[str] | None = None) -> typing.Any:
    models = models or ["m"]
    return SimpleNamespace(
        id=bid,
        type="ollama",
        chat_url=f"{url}/v1/chat/completions",
        models=models,
        resolve_model=lambda h, _m=models: h if h in _m else None,
    )


async def _fallback_run(monkeypatch, inner_chunks, remaining, ns_result=None):
    calls: list[str] = []

    async def inner(*_a, **_k):
        for c in inner_chunks:
            yield c

    async def fake_ns(backend, *_a, **kw):
        calls.append(backend.id)
        return ns_result

    monkeypatch.setattr(st, "_select_stream_fn", lambda *a, **k: inner())
    monkeypatch.setattr(st, "_try_non_streaming", fake_ns)
    gen = st._stream_with_fallback(
        _backend("b0"),
        {},
        "ws",
        "m",
        "p",
        [],
        0.0,
        False,
        [],
        False,
        "",
        "",
        remaining,
        MagicMock(),
        {},
    )
    return await _drain(gen), calls


@pytest.mark.anyio
async def test_no_fallback_after_output_reached_client(monkeypatch) -> None:
    inner = [
        (_delta(content="partial answer") + "\n\n").encode(),
        b'data: {"error": "Backend connection error"}\n\n',
        DONE,
    ]
    chunks, calls = await _fallback_run(monkeypatch, inner, [_backend("b1")])
    assert calls == []
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE


@pytest.mark.anyio
async def test_no_fallback_on_malformed_request(monkeypatch) -> None:
    inner = [b'data: {"error": "Backend returned HTTP 400: bad", "status": 400}\n\n']
    chunks, calls = await _fallback_run(monkeypatch, inner, [_backend("b1")])
    assert calls == [] and b"HTTP 400" in b"".join(chunks)


@pytest.mark.anyio
async def test_fallback_done_not_leaked_before_answer(monkeypatch) -> None:
    from fastapi.responses import JSONResponse

    ok = JSONResponse(
        {"choices": [{"message": {"role": "assistant", "content": "rescued"}}]},
        headers={"x-portal-route": "ws;b1;m"},
    )
    inner = [b'data: {"error": {"message": "boom"}}\n\n', DONE]
    chunks, calls = await _fallback_run(monkeypatch, inner, [_backend("b1")], ok)
    assert calls == ["b1"]
    assert _content(chunks) == "rescued"
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE


def test_content_with_error_word_is_not_an_error_envelope() -> None:
    assert st._stream_error((_delta(content='{"error": 1}') + "\n\n").encode()) is None
    assert st._stream_error(b'data: {"error": "x", "status": 500}\n\n') == 500


# ── non-streaming engine ─────────────────────────────────────────────


class _NSClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.posts: list[str] = []

    async def post(
        self, url: str, json: dict[str, typing.Any], timeout: typing.Any
    ) -> httpx.Response:
        self.posts.append(json["model"])
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


@pytest.fixture
def ns_env(monkeypatch: pytest.MonkeyPatch):
    ws = "test-hardening-ws"
    monkeypatch.setitem(ns.WORKSPACES, ws, {"model_hint": "m"})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: False)
    return ws


def _set_client(monkeypatch, *responses: httpx.Response) -> _NSClient:
    client = _NSClient(list(responses))
    monkeypatch.setattr(ns, "_http_client", client)
    return client


@pytest.mark.anyio
async def test_null_content_reply_is_not_a_failure(monkeypatch, ns_env) -> None:
    _set_client(
        monkeypatch,
        httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": None}}]}
        ),
    )
    assert await ns._try_non_streaming(_backend("b"), {"messages": []}, ns_env, 0.0) is not None


@pytest.mark.anyio
async def test_same_engine_and_model_is_attempted_once(monkeypatch, ns_env) -> None:
    client = _set_client(monkeypatch, httpx.Response(500, json={"error": "x"}))
    tried: dict[tuple[str, str], str] = {}
    for bid in ("general", "security"):
        assert (
            await ns._try_non_streaming(_backend(bid), {"messages": []}, ns_env, 0.0, tried=tried)
            is None
        )
    assert client.posts == ["m"]
    assert "x" in next(iter(tried.values()))


@pytest.mark.anyio
async def test_no_wrong_model_substitution_after_hint_failed(monkeypatch, ns_env) -> None:
    client = _set_client(monkeypatch, httpx.Response(500, json={"error": "x"}))
    tried: dict[tuple[str, str], str] = {}
    await ns._try_non_streaming(_backend("a"), {"messages": []}, ns_env, 0.0, tried=tried)
    other = _backend("b", url="http://other", models=["unrelated"])
    result = await ns._try_non_streaming(
        other, {"messages": []}, ns_env, 0.0, enforce_hint=False, tried=tried
    )
    assert result is None and client.posts == ["m"]


@pytest.mark.anyio
async def test_malformed_request_raises_instead_of_cascading(monkeypatch, ns_env) -> None:
    _set_client(monkeypatch, httpx.Response(400, json={"error": {"message": "bad param"}}))
    with pytest.raises(ns.BackendRequestError) as exc:
        await ns._try_non_streaming(_backend("a"), {"messages": []}, ns_env, 0.0)
    assert exc.value.status_code == 400 and "bad param" in exc.value.detail


@pytest.mark.anyio
async def test_client_tools_stripped_for_non_tool_model(monkeypatch, ns_env) -> None:
    seen: list[dict[str, typing.Any]] = []

    class _C(_NSClient):
        async def post(self, url, json, timeout):  # type: ignore[override]
            seen.append(json)
            return await super().post(url, json, timeout)

    client = _C([httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})])
    monkeypatch.setattr(ns, "_http_client", client)
    body = {"messages": [], "tools": [{"type": "function"}], "portal_no_tools": True}
    await ns._try_non_streaming(_backend("a"), body, ns_env, 0.0)
    assert "tools" not in seen[0] and "portal_no_tools" not in seen[0]


# ── Anthropic compat ─────────────────────────────────────────────────


def test_parallel_tool_results_all_become_tool_messages() -> None:
    body = anthropic_to_openai_body(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "A"},
                        {"type": "tool_result", "tool_use_id": "t2", "content": "B"},
                        {"type": "text", "text": "and?"},
                    ],
                }
            ]
        }
    )
    assert [(m["role"], m.get("tool_call_id")) for m in body["messages"]] == [
        ("tool", "t1"),
        ("tool", "t2"),
        ("user", None),
    ]


@pytest.mark.anyio
async def test_streamed_tool_calls_become_tool_use_blocks() -> None:
    lines = [
        _delta(content="Checking."),
        _delta(
            tool_calls=[{"index": 0, "id": "c1", "function": {"name": "get", "arguments": '{"a"'}}]
        ),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": ":1}"}}]),
        _data({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
        "data: [DONE]",
    ]

    async def it() -> typing.AsyncIterator[str]:
        for line in lines:
            yield line

    events = [
        json.loads(e.split("data: ", 1)[1])
        async for e in openai_stream_to_anthropic_sse(it(), "msg", "m")
    ]
    starts = [e["content_block"]["type"] for e in events if e["type"] == "content_block_start"]
    assert starts == ["text", "tool_use"]
    partial = "".join(
        e["delta"].get("partial_json", "") for e in events if e["type"] == "content_block_delta"
    )
    assert json.loads(partial) == {"a": 1}
    assert next(e for e in events if e["type"] == "message_delta")["delta"]["stop_reason"] == (
        "tool_use"
    )


def test_anthropic_endpoint_accepts_x_api_key(api, monkeypatch) -> None:
    from fastapi.responses import JSONResponse

    import portal.platform.inference.router.handlers as handlers_mod
    from portal.platform.inference.router.auth import PIPELINE_API_KEY

    async def fake_ns(*_a, **_k):
        return JSONResponse(
            {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
            headers={"x-portal-route": "auto-daily;b;m"},
        )

    monkeypatch.setattr(handlers_mod, "_try_non_streaming", fake_ns)
    r = api.post(
        "/v1/messages",
        json={
            "model": "auto-daily",
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={"x-api-key": PIPELINE_API_KEY},
    )
    assert r.status_code == 200, r.text


# ── tool registry + memory write-back ────────────────────────────────


@pytest.mark.anyio
async def test_bad_arguments_do_not_trip_the_tool_breaker(monkeypatch) -> None:
    from portal.platform.inference.tool_registry import ToolDefinition, ToolRegistry

    reg = ToolRegistry()
    tool = ToolDefinition(
        name="t", description="", parameters={}, server_url="http://mcp", server_id="s"
    )
    reg._tools["t"] = tool

    class _C:
        async def post(self, *_a, **_k):
            return httpx.Response(400, json={"error": "code is required"})

    async def _client():
        return _C()

    monkeypatch.setattr(reg, "_client", _client)
    result = await reg.dispatch("t", {})
    assert "code is required" in result["detail"]
    assert tool.healthy and tool.consecutive_failures == 0


def test_owui_task_prompt_is_never_written_back(monkeypatch) -> None:
    ws = "test-hardening-ws"
    monkeypatch.setitem(st.WORKSPACES, ws, {"memory_writeback_all": True})
    task = "### Task:\nGenerate a concise title.\n<chat_history>\nUSER: remember that X\n</chat_history>"
    assert _salient_user_text([{"role": "user", "content": task}], ws) is None
    assert _salient_user_text([{"role": "user", "content": "remember that X"}], ws) == (
        "remember that X"
    )


def test_tool_using_chain_streams_the_chain() -> None:
    gen = st._select_stream_fn(
        _backend("b"),
        {},
        MagicMock(),
        "ws",
        "m",
        "p",
        ["t"],
        0.0,
        [{"model": "m2"}],
        "",
        "",
        False,
        True,
    )
    assert gen.__name__ == "_stream_with_chain"  # type: ignore[attr-defined]
    assert gen.ag_frame.f_locals["primary_tools"] == {"t"}  # type: ignore[attr-defined]


def test_chain_hop_goes_to_a_backend_that_serves_its_model(monkeypatch) -> None:
    omlx = SimpleNamespace(
        id="omlx", chat_url="http://omlx/v1/chat/completions", resolve_model=lambda _h: None
    )
    ollama = _backend("ollama", url="http://ollama", models=["granite:8b"])
    reg = SimpleNamespace(
        get_backend_candidates=lambda _ws: [omlx, ollama], list_healthy_backends=lambda: []
    )
    monkeypatch.setattr(ns, "registry", reg)
    url, body = ns.resolve_hop_target(
        "ws", "granite:8b", omlx.chat_url, {"model": "granite:8b", "chat_template_kwargs": {}}
    )
    assert url == ollama.chat_url
    assert "chat_template_kwargs" not in body


@pytest.mark.anyio
async def test_router_timeout_schedules_one_uncancelled_reload(monkeypatch) -> None:
    import asyncio

    import portal.platform.inference.router.routing as routing

    posts: list[dict[str, typing.Any]] = []
    release = asyncio.Event()

    class _C:
        async def post(self, url, json):
            posts.append(json)
            if json.get("prompt") == routing._build_router_prompt("warmup"):  # the reload
                await release.wait()
                return httpx.Response(200, json={})
            await asyncio.sleep(10)  # cold load outlasts the routing deadline

    monkeypatch.setattr(routing, "_http_client", _C())
    monkeypatch.setattr(routing, "_LLM_ROUTER_ENABLED", True)
    monkeypatch.setattr(routing, "_LLM_ROUTER_TIMEOUT_MS", 10)
    monkeypatch.setattr(routing, "_router_reload_task", None)
    msgs = [{"role": "user", "content": "write a python function"}]
    assert await routing._route_with_llm(msgs) is None
    assert await routing._route_with_llm(msgs) is None
    await asyncio.sleep(0)
    reloads = [p for p in posts if p.get("prompt") == routing._build_router_prompt("warmup")]
    assert len(reloads) == 1 and reloads[0]["keep_alive"] == -1
    release.set()
    await routing._router_reload_task
