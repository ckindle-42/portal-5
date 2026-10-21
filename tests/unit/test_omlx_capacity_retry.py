"""oMLX capacity refusals retry after freeing idle Ollama; a refusal that survives the retry surfaces."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

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
PREFILL_GUARD = (
    b'{"error":{"message":"oMLX prefill memory guard rejected this prompt: Prefill would '
    b"require ~25.79 GB peak (current 18.17 GB + KV+SDPA 7.62 GB) but dynamic ceiling is "
    b'25.61 GB; only 9.66 GB is reclaimable"}}'
)
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


def test_a_short_prefill_refusal_still_frees_and_retries_omlx(monkeypatch) -> None:
    answer = json.dumps({"choices": [{"delta": {"content": "hello"}, "finish_reason": "stop"}]})
    responses = [
        _Resp(400, PREFILL_GUARD),
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

    out = asyncio.run(run())

    assert len(posts) == 2 and freed == [1]
    assert b"hello" in out and b'"error"' not in out


def test_tool_loop_surfaces_a_prefill_refusal_that_survives_the_free_retry(monkeypatch) -> None:
    freed: list[int] = []

    async def fake_free(*_args, **_kwargs):
        freed.append(1)
        return ["idle:30b"]

    monkeypatch.setattr(streaming, "free_ollama_for_omlx", fake_free)
    out, posts = _drive_tool_loop(
        monkeypatch, [_Resp(400, PREFILL_GUARD), _Resp(400, PREFILL_GUARD)]
    )

    assert len(posts) == 2 and freed == [1]
    assert b"estimated prompt size ~" in out
    assert b"25.61 GB" in out


def test_tool_loop_reports_prefill_capacity_when_freeing_cannot_help(monkeypatch) -> None:
    freed: list[int] = []

    async def fake_free(*_args, **_kwargs):
        freed.append(1)
        return []

    monkeypatch.setattr(streaming, "free_ollama_for_omlx", fake_free)
    out, posts = _drive_tool_loop(monkeypatch, [_Resp(400, PREFILL_GUARD)])

    assert len(posts) == 1 and freed == [1]
    assert b"estimated prompt size ~" in out
    assert b"25.61 GB" in out


def _setup_non_streaming(monkeypatch, outcomes: list[httpx.Response], freeable: list[str]):
    calls: list[str] = []

    class _Client:
        async def post(self, url, json=None, timeout=None):  # noqa: A002
            calls.append(url)
            return outcomes.pop(0)

    async def no_room(*_args, **_kwargs):
        return None

    async def free_models(*_args, **_kwargs):
        return freeable

    monkeypatch.setattr(non_streaming, "_http_client", _Client())
    monkeypatch.setattr(non_streaming, "registry", SimpleNamespace(request_timeout=1))
    monkeypatch.setattr(non_streaming, "WORKSPACES", {"capacity-test": {"model_hint": "hint"}})
    monkeypatch.setattr(non_streaming, "_inject_omlx_options", lambda body, _ws: body)
    monkeypatch.setattr(non_streaming, "_model_supports_tools", lambda _model: False)
    monkeypatch.setattr(non_streaming, "_resolve_persona_tools", lambda *_args: [])
    monkeypatch.setattr(bi, "make_room_for_omlx", no_room)
    monkeypatch.setattr(bi, "free_ollama_for_omlx", free_models)
    return calls


def _omlx_backend() -> SimpleNamespace:
    return SimpleNamespace(
        id="omlx",
        type="omlx",
        chat_url="http://omlx.test/v1/chat/completions",
        models=["native-model"],
        resolve_model=lambda _model: "native-model",
    )


def test_non_stream_prefill_refusal_surfaces_capacity_without_ollama_timeout(monkeypatch) -> None:
    response = httpx.Response(
        400,
        content=PREFILL_GUARD,
        request=httpx.Request("POST", "http://omlx.test/v1/chat/completions"),
    )
    calls = _setup_non_streaming(monkeypatch, [response], [])
    monkeypatch.setattr(handlers, "_try_non_streaming", non_streaming._try_non_streaming)
    monkeypatch.setattr(handlers, "_record_error", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(handlers, "trace_span", lambda *_args, **_kwargs: None)
    body = {"messages": [{"role": "user", "content": "hi"}]}
    ollama = SimpleNamespace(
        id="ollama-general",
        type="ollama",
        chat_url="http://ollama.test/v1/chat/completions",
        models=["fallback-model"],
        resolve_model=lambda _model: "fallback-model",
    )
    try:
        asyncio.run(
            handlers._dispatch_non_streaming(
                [_omlx_backend(), ollama],
                body,
                "capacity-test",
                "",
                False,
                time.monotonic(),
            )
        )
    except HTTPException as exc:
        detail = str(exc.detail)
    else:
        raise AssertionError("prefill refusal should surface as a capacity error")

    assert len(calls) == 1
    assert "estimated prompt size ~" in detail
    assert "25.61 GB" in detail


def test_non_stream_prefill_refusal_raises_after_the_free_retry(monkeypatch) -> None:
    refusals = [
        httpx.Response(
            400,
            content=PREFILL_GUARD,
            request=httpx.Request("POST", "http://omlx.test/v1/chat/completions"),
        ),
        httpx.Response(
            400,
            content=PREFILL_GUARD,
            request=httpx.Request("POST", "http://omlx.test/v1/chat/completions"),
        ),
    ]
    calls = _setup_non_streaming(monkeypatch, refusals, ["idle:30b"])

    with pytest.raises(non_streaming.BackendRequestError) as excinfo:
        asyncio.run(
            non_streaming._try_non_streaming(
                _omlx_backend(),
                {"messages": [{"role": "user", "content": "hi"}]},
                "capacity-test",
                time.monotonic(),
                tried={},
            )
        )

    assert len(calls) == 2
    assert "estimated prompt size ~" in excinfo.value.detail


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
    assert len(posts) == 2 and b'"error"' in out

    out, posts = _drive_tool_loop(monkeypatch, [httpx.ReadTimeout("slow")])
    assert len(posts) == 1 and b'"error"' in out  # a read timeout may have started generating
