"""Streaming and non-streaming must recover from the same engine failure the same way.

Each scenario drives both dispatchers — ``handlers._dispatch_non_streaming`` and
``streaming._stream_with_fallback`` — against one scripted engine queue, and asserts the
same engine calls and the same answer. A recovery that exists on only one path is a
production bug the non-streaming UAT cannot see.
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from portal.platform.inference import load_guard
from portal.platform.inference.router import backend_introspect as bi
from portal.platform.inference.router import handlers, non_streaming, streaming
from portal.platform.inference.router.auth import PIPELINE_API_KEY

_WORKSPACE = "parity-test"
_OMLX_URL = "http://omlx.test/v1/chat/completions"
_OLLAMA_URL = "http://ollama.test/v1/chat/completions"
_HEADERS = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}
_BODY: dict[str, Any] = {"messages": [{"role": "user", "content": "hi"}]}


@pytest.fixture
def app_client() -> Any:
    """The real app with a one-candidate fake registry, as the other handler tests use."""
    import portal.platform.inference.router.handlers as handlers_mod
    from portal.platform.inference.router_pipe import app
    from tests.unit.test_pipeline import _make_fake_backend

    with TestClient(app) as client:
        handlers_mod.registry = _make_fake_backend()
        yield client
    handlers_mod.registry = None


#: oMLX's two capacity refusals: the 400 prefill guard and the 507 load ceiling.
PREFILL_GUARD = b'{"error":{"message":"prefill memory guard: would exceed the memory ceiling"}}'
LOAD_CEILING = b'{"error":{"message":"does not fit under the dynamic memory ceiling"}}'


def _omlx() -> SimpleNamespace:
    return SimpleNamespace(
        id="omlx-parity",
        type="omlx",
        chat_url=_OMLX_URL,
        models=["native-model"],
        resolve_model=lambda _hint: "native-model",
    )


def _ollama() -> SimpleNamespace:
    return SimpleNamespace(
        id="ollama-parity",
        type="ollama",
        chat_url=_OLLAMA_URL,
        models=["fallback-model"],
        resolve_model=lambda _hint: "fallback-model",
    )


def _served() -> httpx.Response:
    """The answer a backend that can serve returns.

    A stream's fallback candidates are read through ``_try_non_streaming`` (JSON) and
    re-framed as SSE, so the JSON body is what both transports consume here.
    """
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "rescued"}}]}
    )


class _Open:
    def __init__(self, reply: httpx.Response) -> None:
        self._reply = reply

    async def __aenter__(self) -> httpx.Response:
        return self._reply

    async def __aexit__(self, *_exc: object) -> None:
        return None


class _Scripted:
    """One reply queue for both transports; records every URL called."""

    def __init__(self, replies: list[httpx.Response]) -> None:
        self._replies = list(replies)
        self.calls: list[str] = []

    def _reply(self, url: str) -> httpx.Response:
        self.calls.append(url)
        reply = self._replies.pop(0)
        reply.request = httpx.Request("POST", url)
        return reply

    async def post(self, url: str, json: Any = None, timeout: Any = None) -> httpx.Response:  # noqa: A002
        return self._reply(url)

    def stream(self, method: str, url: str, json: Any = None) -> _Open:  # noqa: A002
        return _Open(self._reply(url))


class _Frees:
    """What each ``free_ollama_for_omlx`` call returns, in order; records every call."""

    def __init__(self, results: list[list[str]]) -> None:
        self._results = list(results)
        self.calls: list[list[str]] = []

    async def __call__(self, *_args: Any, **_kwargs: Any) -> list[str]:
        freed = self._results.pop(0) if self._results else []
        self.calls.append(freed)
        return freed


def _install(monkeypatch: pytest.MonkeyPatch, replies: list[httpx.Response], frees: _Frees):
    client = _Scripted(replies)
    monkeypatch.setattr(non_streaming, "_http_client", client)
    monkeypatch.setattr(streaming, "_http_client", client)
    monkeypatch.setattr(non_streaming, "registry", SimpleNamespace(request_timeout=5))
    monkeypatch.setitem(non_streaming.WORKSPACES, _WORKSPACE, {"model_hint": "hint"})
    monkeypatch.setattr(non_streaming, "_inject_omlx_options", lambda body, _ws: body)
    monkeypatch.setattr(non_streaming, "_inject_ollama_options", lambda body, _ws: body)
    monkeypatch.setattr(non_streaming, "_model_supports_tools", lambda _model: False)
    monkeypatch.setattr(non_streaming, "_resolve_persona_tools", lambda *_args: [])
    monkeypatch.setattr(
        streaming,
        "_backend_type_for_url",
        lambda url: "omlx" if "omlx" in url else "ollama",
    )
    monkeypatch.setattr(bi, "free_ollama_for_omlx", frees)
    monkeypatch.setattr(streaming, "free_ollama_for_omlx", frees)
    return client


def _drive_non_streaming(backends: list[Any]) -> dict[str, Any]:
    response = asyncio.run(
        handlers._dispatch_non_streaming(backends, _BODY, _WORKSPACE, "", False, time.monotonic())
    )
    return json.loads(response.body)


def _drive_streaming(backends: list[Any]) -> str:
    backend = backends[0]
    body = {**_BODY, "model": backend.models[0]}
    gen = streaming._stream_with_fallback(
        backend,
        _BODY,
        _WORKSPACE,
        backend.models[0],
        "",
        [],
        0.0,
        False,
        [],
        False,
        "",
        "",
        backends[1:],
        MagicMock(),
        body,
    )

    async def drain() -> str:
        out = b""
        async for chunk in gen:
            out += chunk
        return out.decode()

    return asyncio.run(drain())


def _answer(stream: bool, backends: list[Any]) -> str:
    if stream:
        return _drive_streaming(backends)
    data = _drive_non_streaming(backends)
    return str(data["choices"][0]["message"]["content"])


@pytest.mark.parametrize(
    "refusal", [PREFILL_GUARD, LOAD_CEILING], ids=["prefill-400", "ceiling-507"]
)
@pytest.mark.parametrize("stream", [False, True], ids=["non-streaming", "streaming"])
def test_a_capacity_refusal_frees_idle_ollama_and_retries_the_same_engine(
    monkeypatch: pytest.MonkeyPatch, stream: bool, refusal: bytes
) -> None:
    """Both paths: refuse → free what oMLX cannot reclaim → re-issue → sibling serves."""
    status = 400 if refusal is PREFILL_GUARD else 507
    frees = _Frees([["idle:30b"]])
    client = _install(
        monkeypatch,
        [
            httpx.Response(status, content=refusal),
            httpx.Response(status, content=refusal),
            _served(),
        ],
        frees,
    )

    assert "rescued" in _answer(stream, [_omlx(), _ollama()])

    assert client.calls == [_OMLX_URL, _OMLX_URL, _OLLAMA_URL]
    assert frees.calls[0] == ["idle:30b"]


@pytest.mark.parametrize("stream", [False, True], ids=["non-streaming", "streaming"])
def test_with_nothing_idle_to_free_the_refusal_cascades_without_a_retry(
    monkeypatch: pytest.MonkeyPatch, stream: bool
) -> None:
    frees = _Frees([[]])
    client = _install(
        monkeypatch,
        [httpx.Response(400, content=PREFILL_GUARD), _served()],
        frees,
    )

    assert "rescued" in _answer(stream, [_omlx(), _ollama()])

    assert client.calls == [_OMLX_URL, _OLLAMA_URL]
    assert frees.calls[0] == []


@pytest.mark.parametrize("stream", [False, True], ids=["non-streaming", "streaming"])
def test_the_model_a_request_failed_over_from_is_not_left_evictable(
    monkeypatch: pytest.MonkeyPatch, stream: bool
) -> None:
    """P-2 on both paths: the seat this request left is protected from load_guard."""
    protected: list[tuple[str, str]] = []

    def protect(engine: str, model: str) -> None:
        protected.append((engine, model))

    client = _install(
        monkeypatch,
        [httpx.Response(500, json={"error": "boom"}), _served()],
        _Frees([]),
    )
    monkeypatch.setattr(load_guard, "protect_failover", protect)
    monkeypatch.setattr(streaming, "protect_failover", protect)

    assert "rescued" in _answer(stream, [_omlx(), _ollama()])

    assert client.calls == [_OMLX_URL, _OLLAMA_URL]
    assert protected == [("omlx", "native-model")]


def test_a_single_candidate_stream_frees_idle_ollama_before_a_large_omlx_prompt(
    monkeypatch: pytest.MonkeyPatch, app_client: TestClient
) -> None:
    """The non-streaming path makes room before every attempt; a lone stream used to skip it."""
    import portal.platform.inference.router.handlers as handlers_mod

    events: list[Any] = []

    async def build(body: dict[str, Any], *_args: Any) -> tuple[Any, ...]:
        return body, [], False, True

    def select_backend(_workspace: str, _candidates: list[Any]) -> tuple[Any, ...]:
        return _omlx(), "native-model", "", [], "", ""

    async def frames(*_args: Any, **_kwargs: Any) -> Any:
        events.append("frame")
        yield b"data: [DONE]\n\n"

    async def room(backend: Any, _body: dict[str, Any]) -> None:
        events.append(("room", backend.type))

    monkeypatch.setattr(handlers_mod, "_build_streaming_request", build)
    monkeypatch.setattr(handlers_mod, "_select_streaming_backend", select_backend)
    monkeypatch.setattr(handlers_mod, "_select_stream_fn", lambda *_a, **_k: frames())
    monkeypatch.setattr(streaming, "make_room_for_omlx", room)
    response = app_client.post(
        "/v1/chat/completions",
        json={"model": "auto-daily", "stream": True, **_BODY},
        headers=_HEADERS,
    )

    assert response.status_code == 200, response.text
    assert events == [("room", "omlx"), "frame"]


def test_a_single_candidate_stream_retries_an_omlx_capacity_refusal(
    monkeypatch: pytest.MonkeyPatch, app_client: TestClient
) -> None:
    """A lone stream has no fallback driver: it must free and re-issue the request itself."""
    import portal.platform.inference.router.handlers as handlers_mod

    answer = {"choices": [{"delta": {"content": "rescued"}, "finish_reason": "stop"}]}
    sse = f"data: {json.dumps(answer)}\n\ndata: [DONE]\n\n"
    client = _Scripted(
        [
            httpx.Response(400, content=PREFILL_GUARD),
            httpx.Response(200, content=sse.encode()),
        ]
    )
    frees = _Frees([["idle:30b"]])

    async def build(body: dict[str, Any], *_args: Any) -> tuple[Any, ...]:
        return body, [], False, True

    def select_backend(_workspace: str, _candidates: list[Any]) -> tuple[Any, ...]:
        return _omlx(), "native-model", "", [], "", ""

    monkeypatch.setattr(handlers_mod, "_build_streaming_request", build)
    monkeypatch.setattr(handlers_mod, "_select_streaming_backend", select_backend)
    monkeypatch.setattr(streaming, "_http_client", client)
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "omlx")
    monkeypatch.setattr(streaming, "free_ollama_for_omlx", frees)
    response = app_client.post(
        "/v1/chat/completions",
        json={"model": "auto-daily", "stream": True, **_BODY},
        headers=_HEADERS,
    )

    assert response.status_code == 200, response.text
    assert "rescued" in response.text
    assert client.calls == [_OMLX_URL, _OMLX_URL]
    assert frees.calls == [["idle:30b"]]
