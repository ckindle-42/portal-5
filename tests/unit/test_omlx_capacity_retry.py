"""oMLX capacity refusals (the 400 prefill guard, the 507 load ceiling) free idle Ollama once and
retry oMLX, on every path; a free never takes a busy or protected Ollama model; a refusal that
survives still falls back to the next candidate, and only an exhausted chain reports capacity."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from portal.platform.inference import load_guard
from portal.platform.inference.router import backend_introspect as bi
from portal.platform.inference.router import handlers, non_streaming, streaming
from portal.platform.inference.router.non_streaming import (
    is_omlx_capacity_refusal,
    is_omlx_prefill_refusal,
)

LOAD_CEILING = (
    b'{"error":{"message":"Model \'unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit\' (21.16GB) does not fit '
    b'under the dynamic memory ceiling (8.12GB). Close other apps to free RAM"}}'
)
PREFILL_GUARD = b'{"error":{"message":"prefill memory guard: would exceed the memory ceiling"}}'
OLLAMA_LOAD = b'{"error":"model requires 27.1 GiB, 26.7 GiB available; cannot load"}'


def test_the_predicate_matches_both_omlx_refusals_and_nothing_else() -> None:
    assert is_omlx_capacity_refusal(507, LOAD_CEILING)
    assert is_omlx_capacity_refusal(400, PREFILL_GUARD)
    assert is_omlx_prefill_refusal(400, PREFILL_GUARD)
    assert not is_omlx_prefill_refusal(507, LOAD_CEILING)
    assert not is_omlx_prefill_refusal(400, b'{"error":"invalid parameter temperature"}')
    assert not is_omlx_capacity_refusal(400, b'{"error":"invalid parameter temperature"}')
    assert not is_omlx_capacity_refusal(500, LOAD_CEILING)


def test_freeable_skips_the_router_busy_and_protected_models(monkeypatch) -> None:
    guard = SimpleNamespace(
        busy=lambda engine, model: 1 if model == "busy:7b" else 0,
        protected=lambda engine: {"failover:9b"} if engine == load_guard.OLLAMA else set(),
    )
    monkeypatch.setattr(load_guard, "GUARD", guard)
    names = ["router:1b", "busy:7b", "failover:9b", "idle:30b"]
    assert bi._freeable(names, "router:1b") == ["idle:30b"]


def test_an_omlx_protection_never_shields_an_ollama_model(monkeypatch) -> None:
    class _Guard(load_guard.LoadGuard):
        def __init__(self) -> None:  # bypass the real constructor
            self._protected = {("omlx", "same-name"): float("inf")}
            self._busy = {}

    monkeypatch.setattr(load_guard, "GUARD", _Guard())
    assert bi._freeable(["same-name"], "router") == ["same-name"]


class _Resp:
    def __init__(self, status: int, body: bytes = b"", lines: list[str] | None = None) -> None:
        self.status_code = status
        self._body = body
        self._lines = lines or []

    async def aread(self) -> bytes:
        return self._body

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


def test_a_507_on_the_tool_loop_frees_once_and_retries_omlx(monkeypatch) -> None:
    answer = json.dumps({"choices": [{"delta": {"content": "hello"}, "finish_reason": "stop"}]})
    responses = [
        _Resp(507, LOAD_CEILING),
        _Resp(200, lines=[f"data: {answer}", "data: [DONE]"]),
    ]
    posts: list[str] = []
    freed: list[int] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            posts.append(url)
            return _Stream(responses.pop(0))

    async def fake_free(*_a, **_k):
        freed.append(1)
        return ["idle:30b"]

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "omlx")
    monkeypatch.setattr(streaming, "free_ollama_for_omlx", fake_free)

    async def run() -> bytes:
        out = b""
        gen = streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}], "model": "m"},
            "auto-daily",
            "m",
            "",
            set(),
        )
        async for chunk in gen:
            out += chunk
        return out

    out = asyncio.run(run())

    assert len(posts) == 2 and freed == [1]
    assert b"hello" in out
    assert b'"error"' not in out  # the 507 never reaches the client


def _drive_tool_loop(monkeypatch, outcomes: list) -> tuple[bytes, list[str]]:
    """Run the tool loop against scripted POST outcomes (a _Resp, or an exception to raise)."""
    posts: list[str] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            posts.append(url)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return _Stream(outcome)

    async def no_engine(*_a, **_k):
        return False

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "omlx")
    from portal.platform.inference.router import backend_introspect

    monkeypatch.setattr(backend_introspect, "model_still_running", no_engine)

    async def run() -> bytes:
        out = b""
        async for chunk in streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}], "model": "m"},
            "auto-daily",
            "m",
            "",
            set(),
        ):
            out += chunk
        return out

    return asyncio.run(run()), posts


def test_a_connect_timeout_retries_the_same_backend_once(monkeypatch) -> None:
    """The connection never opened, so nothing was sent: retry instead of failing the turn over."""
    import httpx

    answer = json.dumps({"choices": [{"delta": {"content": "hello"}, "finish_reason": "stop"}]})
    out, posts = _drive_tool_loop(
        monkeypatch,
        [httpx.ConnectTimeout("connect"), _Resp(200, lines=[f"data: {answer}", "data: [DONE]"])],
    )
    assert len(posts) == 2 and b"hello" in out and b'"error"' not in out


def test_a_second_connect_timeout_and_any_read_timeout_surface_as_errors(monkeypatch) -> None:
    import httpx

    out, posts = _drive_tool_loop(
        monkeypatch, [httpx.ConnectTimeout("a"), httpx.ConnectTimeout("b")]
    )
    assert len(posts) == 2
    assert "Backend timed out and no model is loaded" in out.decode()
    assert b'"error"' not in out and out.endswith(b"data: [DONE]\n\n")

    out, posts = _drive_tool_loop(monkeypatch, [httpx.ReadTimeout("slow")])
    # A read timeout may have started generating: report it, never retry.
    assert len(posts) == 1
    assert "Backend timed out and no model is loaded" in out.decode()
    assert b'"error"' not in out and out.endswith(b"data: [DONE]\n\n")


# ── a refusal falls back to the Ollama sibling; capacity is the last resort ──

_CAPACITY_FRAME = streaming._backend_error_chunk(400, PREFILL_GUARD)


def _omlx_backend() -> SimpleNamespace:
    return SimpleNamespace(
        id="omlx-general",
        type="omlx",
        chat_url="http://omlx.test/v1/chat/completions",
        models=["native-model"],
        resolve_model=lambda _model: "native-model",
    )


def _ollama_backend() -> SimpleNamespace:
    return SimpleNamespace(
        id="ollama-general",
        type="ollama",
        chat_url="http://ollama.test/v1/chat/completions",
        models=["fallback-model"],
        resolve_model=lambda _model: "fallback-model",
    )


class _PostClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.posts: list[str] = []

    async def post(self, url, json=None, timeout=None):  # noqa: A002
        self.posts.append(url)
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def _setup_non_streaming(
    monkeypatch, outcomes: list[httpx.Response], freeable: list[str] | None = None
) -> _PostClient:
    client = _PostClient(list(outcomes))

    async def free_models(*_args, **_kwargs):
        return list(freeable or [])

    monkeypatch.setattr(non_streaming, "_http_client", client)
    monkeypatch.setattr(non_streaming, "registry", SimpleNamespace(request_timeout=1))
    monkeypatch.setitem(non_streaming.WORKSPACES, "capacity-test", {"model_hint": "hint"})
    monkeypatch.setattr(non_streaming, "_inject_omlx_options", lambda body, _ws: body)
    monkeypatch.setattr(non_streaming, "_model_supports_tools", lambda _model: False)
    monkeypatch.setattr(non_streaming, "_resolve_persona_tools", lambda *_args: [])
    monkeypatch.setattr(bi, "free_ollama_for_omlx", free_models)
    monkeypatch.setattr(handlers, "_try_non_streaming", non_streaming._try_non_streaming)
    monkeypatch.setattr(handlers, "_record_error", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(handlers, "trace_span", lambda *_args, **_kwargs: None)
    return client


def _dispatch(candidates: list[SimpleNamespace]) -> JSONResponse:
    return asyncio.run(
        handlers._dispatch_non_streaming(
            candidates,
            {"messages": [{"role": "user", "content": "hi"}]},
            "capacity-test",
            "",
            False,
            time.monotonic(),
        )
    )


def test_non_stream_prefill_refusal_falls_back_to_the_ollama_sibling(monkeypatch) -> None:
    refusal = httpx.Response(400, content=PREFILL_GUARD)
    served = httpx.Response(200, json={"choices": [{"message": {"content": "rescued"}}]})
    client = _setup_non_streaming(monkeypatch, [refusal, served])

    response = _dispatch([_omlx_backend(), _ollama_backend()])

    assert client.posts == [
        "http://omlx.test/v1/chat/completions",
        "http://ollama.test/v1/chat/completions",
    ]
    assert json.loads(response.body)["choices"][0]["message"]["content"] == "rescued"


def test_non_stream_prefill_refusal_reports_capacity_once_the_chain_is_exhausted(
    monkeypatch,
) -> None:
    refusal = httpx.Response(400, content=PREFILL_GUARD)
    failed_sibling = httpx.Response(500, json={"error": "boom"})
    client = _setup_non_streaming(monkeypatch, [refusal, failed_sibling])

    with pytest.raises(HTTPException) as excinfo:
        _dispatch([_omlx_backend(), _ollama_backend()])

    assert len(client.posts) == 2  # the Ollama sibling was tried before the error surfaced
    assert excinfo.value.status_code == 400
    assert "estimated prompt size ~" in excinfo.value.detail
    assert "would exceed the memory ceiling" in excinfo.value.detail


async def _drain(gen) -> bytes:
    out = b""
    async for chunk in gen:
        out += chunk
    return out


async def _stream_fallback(
    monkeypatch, inner, remaining, ns_result, freeable: list[str] | None = None
) -> tuple[bytes, list[str]]:
    calls: list[str] = []

    async def fake_ns(backend, *_args, **_kwargs):
        calls.append(backend.id)
        return ns_result

    async def fake_free(*_args, **_kwargs):
        return list(freeable or [])

    async def inner_stream(*_args, **_kwargs):
        for chunk in inner:
            yield chunk

    monkeypatch.setattr(streaming, "_select_stream_fn", lambda *_a, **_k: inner_stream())
    monkeypatch.setattr(streaming, "_try_non_streaming", fake_ns)
    monkeypatch.setattr(streaming, "free_ollama_for_omlx", fake_free)
    gen = streaming._stream_with_fallback(
        _omlx_backend(),
        {},
        "capacity-test",
        "m",
        "",
        [],
        0.0,
        False,
        [],
        False,
        "",
        "",
        remaining,
        SimpleNamespace(release=lambda: None, release_if_attached=lambda: None),
        {},
    )
    return await _drain(gen), calls


@pytest.mark.anyio
async def test_streamed_prefill_refusal_falls_back_to_the_ollama_sibling(monkeypatch) -> None:
    ok = JSONResponse(
        {"choices": [{"message": {"role": "assistant", "content": "rescued"}}]},
        headers={"x-portal-route": "capacity-test;ollama-general;fallback-model"},
    )

    out, calls = await _stream_fallback(monkeypatch, [_CAPACITY_FRAME], [_ollama_backend()], ok)

    assert calls == ["ollama-general"]
    assert b"rescued" in out
    assert b"estimated prompt size" not in out


@pytest.mark.anyio
async def test_stream_chain_exhausted_reports_the_capacity_error(monkeypatch) -> None:
    out, calls = await _stream_fallback(monkeypatch, [_CAPACITY_FRAME], [_ollama_backend()], None)

    assert calls == ["ollama-general"]  # the sibling was tried before the error surfaced
    assert b"Backend returned HTTP 400" in out  # the refusal still names its status
    assert b"estimated prompt size ~" in out
    assert b"would exceed the memory ceiling" in out
    # and the client gets a readable ending, not a bare error frame
    assert b'"error"' not in out
    assert b'"finish_reason": "stop"' in out and out.endswith(b"data: [DONE]\n\n")


@pytest.mark.anyio
async def test_fallback_served_after_the_free_retry_still_wins(monkeypatch) -> None:
    """The free-idle-Ollama retry runs first; when it frees something the refusal still falls back."""
    ok = JSONResponse(
        {"choices": [{"message": {"role": "assistant", "content": "rescued"}}]},
        headers={"x-portal-route": "capacity-test;ollama-general;fallback-model"},
    )

    out, calls = await _stream_fallback(
        monkeypatch, [_CAPACITY_FRAME, _CAPACITY_FRAME], [_ollama_backend()], ok, ["idle:30b"]
    )

    assert calls == ["ollama-general"]
    assert b"rescued" in out


def test_tool_loop_prefill_refusal_falls_back_to_the_ollama_sibling(monkeypatch) -> None:
    """The tool-loop path emits the guard envelope, which the fallback wrapper turns into a fallback."""
    ok = JSONResponse(
        {"choices": [{"message": {"role": "assistant", "content": "rescued"}}]},
        headers={"x-portal-route": "capacity-test;ollama-general;fallback-model"},
    )
    posts: list[str] = []

    class _Client:
        def stream(self, method, url, json=None):  # noqa: A002
            posts.append(url)
            return _Stream(_Resp(400, PREFILL_GUARD))

    async def fake_ns(backend, *_args, **_kwargs):
        return ok

    async def fake_free(*_args, **_kwargs):
        return []

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "omlx")
    monkeypatch.setattr(streaming, "free_ollama_for_omlx", fake_free)
    monkeypatch.setattr(streaming, "_try_non_streaming", fake_ns)
    monkeypatch.setattr(
        streaming,
        "_select_stream_fn",
        lambda *_a, **_k: streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}], "model": "m"},
            "capacity-test",
            "m",
            "",
            set(),
        ),
    )

    async def run() -> bytes:
        gen = streaming._stream_with_fallback(
            _omlx_backend(),
            {},
            "capacity-test",
            "m",
            "",
            [],
            0.0,
            True,
            [],
            False,
            "",
            "",
            [_ollama_backend()],
            SimpleNamespace(release=lambda: None, release_if_attached=lambda: None),
            {"messages": [{"role": "user", "content": "hi"}], "model": "m"},
        )
        return await _drain(gen)

    out = asyncio.run(run())

    assert posts == ["http://omlx.test/v1/chat/completions"]
    assert b"rescued" in out
    assert b"estimated prompt size" not in out


def test_non_stream_repeated_refusal_after_a_free_retry_still_cascades(monkeypatch) -> None:
    refusals = [
        httpx.Response(400, content=PREFILL_GUARD),
        httpx.Response(400, content=PREFILL_GUARD),
    ]
    served = httpx.Response(200, json={"choices": [{"message": {"content": "rescued"}}]})
    client = _setup_non_streaming(monkeypatch, [*refusals, served], freeable=["idle:30b"])

    response = _dispatch([_omlx_backend(), _ollama_backend()])

    assert client.posts == [
        "http://omlx.test/v1/chat/completions",  # refused
        "http://omlx.test/v1/chat/completions",  # retried after freeing idle Ollama
        "http://ollama.test/v1/chat/completions",  # refused again — the sibling serves it
    ]
    assert json.loads(response.body)["choices"][0]["message"]["content"] == "rescued"


@pytest.mark.anyio
async def test_a_fallback_candidates_refusal_does_not_stop_the_chain(monkeypatch) -> None:
    """The non-streaming fallbacks cascade too, so an oMLX sibling mid-chain cannot end the turn."""
    ok = JSONResponse(
        {"choices": [{"message": {"role": "assistant", "content": "rescued"}}]},
        headers={"x-portal-route": "capacity-test;ollama-general;fallback-model"},
    )

    async def fake_ns(backend, *_args, **_kwargs):
        if backend.type == "omlx":
            raise non_streaming.BackendRequestError(
                400,
                "oMLX prefill memory guard refused estimated prompt size ~1,000 tokens: ceiling",
            )
        return ok

    async def fake_free(*_args, **_kwargs):
        return []

    async def inner_stream(*_args, **_kwargs):
        yield _CAPACITY_FRAME

    monkeypatch.setattr(streaming, "_select_stream_fn", lambda *_a, **_k: inner_stream())
    monkeypatch.setattr(streaming, "_try_non_streaming", fake_ns)
    monkeypatch.setattr(streaming, "free_ollama_for_omlx", fake_free)
    gen = streaming._stream_with_fallback(
        _omlx_backend(),
        {},
        "capacity-test",
        "m",
        "",
        [],
        0.0,
        False,
        [],
        False,
        "",
        "",
        [_omlx_backend(), _ollama_backend()],
        SimpleNamespace(release=lambda: None, release_if_attached=lambda: None),
        {},
    )
    out = await _drain(gen)

    assert b"rescued" in out
    assert b"estimated prompt size" not in out
