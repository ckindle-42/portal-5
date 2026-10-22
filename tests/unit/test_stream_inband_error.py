"""A backend error written *inside* an already-started stream must end the client's
stream well-formed: the error visible, a finish_reason, and one [DONE].

Ollama's qwen3coder tool parser aborts on a malformed tool call and writes
``{"error": ...}`` into the 200 SSE body (ollama#18563); an OpenAI-compatible
client that requires a finish_reason reports "stream ended without finish_reason".
"""

from __future__ import annotations

import json
import logging
import typing
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

import portal.platform.inference.router.non_streaming as ns
import portal.platform.inference.router.streaming as st
from portal.platform.inference.router.correlation import set_correlation_id

DONE = b"data: [DONE]\n\n"
ERROR_MSG = "XML syntax error on line 58: element <function> closed by </parameter>"
NATIVE_ERROR = json.dumps({"error": ERROR_MSG})
SSE_ERROR = "data: " + json.dumps({"error": {"message": ERROR_MSG, "type": "api_error"}})
ERROR_LINES = pytest.mark.parametrize(
    "error_line", [NATIVE_ERROR, SSE_ERROR], ids=["ollama-native", "openai-sse"]
)


def _delta(**delta: typing.Any) -> str:
    return "data: " + json.dumps({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]})


TEXT = _delta(content="Let me restructure:")
TOOL_CALL = _delta(
    tool_calls=[
        {
            "index": 0,
            "id": "call_1",
            "function": {"name": "write", "arguments": '{"path": "app.py", "content": "x'},
        }
    ]
)
TOOLS = [{"type": "function", "function": {"name": "write", "parameters": {}}}]


class _Resp:
    def __init__(self, lines: list[str], status: int = 200, body: bytes = b"") -> None:
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


@pytest.fixture(autouse=True)
def _correlation_id() -> typing.Iterator[None]:
    set_correlation_id("corr-inband-test")
    yield
    set_correlation_id("")


def _serve(client: MagicMock, *responses: _Resp) -> None:
    queue = list(responses)
    client.stream.side_effect = lambda *_a, **_k: _Ctx(queue.pop(0))


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


def _assert_well_formed(chunks: list[bytes]) -> None:
    """The OpenAI-compatible terminal contract: one finish_reason, then one [DONE]."""
    reasons = [
        ch["finish_reason"]
        for p in _payloads(chunks)
        for ch in p.get("choices") or []
        if ch.get("finish_reason")
    ]
    assert reasons, "no finish_reason reached the client"
    assert reasons[-1] == "stop"
    assert chunks.count(DONE) == 1
    assert chunks[-1] == DONE


# ── no-tools path ────────────────────────────────────────────────────


@ERROR_LINES
@pytest.mark.anyio
async def test_guarded_stream_surfaces_inband_error_after_content(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch, caplog, error_line: str
) -> None:
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(st, "_record_error", lambda ws, kind: recorded.append((ws, kind)))
    _serve(stream_client, _Resp([TEXT, error_line]))

    with caplog.at_level(logging.ERROR, logger="portal.platform.inference.router.streaming"):
        chunks = await _drain(
            st._stream_from_backend_guarded("http://x/v1/chat/completions", {}, "ws", "m")
        )

    assert "Let me restructure:" in _content(chunks)
    assert ERROR_MSG in _content(chunks)
    assert st.NO_ANSWER_MESSAGE not in _content(chunks)
    _assert_well_formed(chunks)
    assert recorded == [("ws", "backend_in_band_error")]
    assert any(
        "corr-inband-test" in r.getMessage() and ERROR_MSG in r.getMessage() for r in caplog.records
    )


# ── tool-loop path ───────────────────────────────────────────────────


@pytest.mark.parametrize("prefix", [TEXT, TOOL_CALL], ids=["mid-content", "mid-tool-call"])
@ERROR_LINES
@pytest.mark.anyio
async def test_tool_loop_surfaces_inband_error_without_dispatching(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch, prefix: str, error_line: str
) -> None:
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(st, "_record_error", lambda ws, kind: recorded.append((ws, kind)))
    _serve(stream_client, _Resp([prefix, error_line]))

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://x/v1/chat/completions",
            {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS},
            "ws",
            "m",
            "p",
            {"write"},
        )
    )

    assert ERROR_MSG in _content(chunks)
    assert st.NO_ANSWER_MESSAGE not in _content(chunks)
    assert not [
        d
        for p in _payloads(chunks)
        for d in [(p.get("choices") or [{}])[0].get("delta") or {}]
        if d.get("tool_calls")
    ]
    _assert_well_formed(chunks)
    assert recorded == [("ws", "backend_in_band_error")]
    assert stream_client.stream.call_count == 1
    assert stream_client.post.call_count == 0  # no empty-hop rescue retry


@ERROR_LINES
@pytest.mark.anyio
async def test_fallback_wrapper_does_not_retry_after_inband_error(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch, error_line: str
) -> None:
    """The error is surfaced, not swallowed by a silent non-streaming retry."""
    from fastapi.responses import JSONResponse

    rescued = JSONResponse(
        {"choices": [{"message": {"role": "assistant", "content": "rescued"}}]},
        headers={"x-portal-route": "ws;b1;m"},
    )
    tried: list[tuple[str, str]] = []

    async def fake_ns(*_a, **_k):
        tried.append(("b1", "m"))
        return rescued

    monkeypatch.setattr(st, "_try_non_streaming", fake_ns)
    _serve(stream_client, _Resp([TEXT, error_line]))
    backend = SimpleNamespace(
        id="b0", type="ollama", chat_url="http://x/v1/chat/completions", models=["m"]
    )
    remaining = [SimpleNamespace(id="b1", type="ollama", chat_url="http://x", models=["m"])]

    chunks = await _drain(
        st._stream_with_fallback(
            backend,
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
    )

    assert tried == []
    assert "rescued" not in _content(chunks)
    assert ERROR_MSG in _content(chunks)
    _assert_well_formed(chunks)


@pytest.mark.anyio
async def test_ollama_native_error_through_transport_ends_well_formed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production chain: Ollama /api/chat NDJSON → OllamaNativeTransport → tool loop."""
    from portal.platform.inference.ollama_native import OllamaNativeTransport

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion", "tools"]})
        native = json.dumps(
            {"model": "m", "message": {"role": "assistant", "content": "Let me restructure:"}}
        )
        return httpx.Response(200, content=f"{native}\n{NATIVE_ERROR}\n".encode())

    transport = OllamaNativeTransport(httpx.MockTransport(handler), is_ollama=lambda _b: True)
    async with httpx.AsyncClient(transport=transport) as client:
        monkeypatch.setattr(st, "_http_client", client)
        chunks = await _drain(
            st._stream_with_tool_loop_impl(
                "http://ollama:11434/v1/chat/completions",
                {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS, "stream": True},
                "ws",
                "m",
                "p",
                {"write"},
            )
        )

    assert ERROR_MSG in _content(chunks)
    _assert_well_formed(chunks)


# ── unchanged behaviour ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_normal_stream_is_byte_identical(stream_client: MagicMock) -> None:
    frame = 'data: {"choices": [{"index": 0, "delta": {"content": "Hello"}}]}'
    _serve(stream_client, _Resp([frame, "data: [DONE]"]))

    chunks = await _drain(
        st._stream_from_backend_guarded("http://x/v1/chat/completions", {}, "ws", "m")
    )

    assert chunks == [
        b'data: {"choices": [{"index": 0, "delta": {"content": "Hello"}}]}\n\n',
        b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n',
        DONE,
    ]


# ── non-streaming ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_non_streaming_reports_inband_error_instead_of_truncated_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = "inband-ns-ws"
    monkeypatch.setitem(ns.WORKSPACES, ws, {"model_hint": "m"})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: False)
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(ns, "_record_error", lambda w, kind: recorded.append((w, kind)))

    class _Client:
        async def post(self, url: str, json: dict[str, typing.Any], timeout: typing.Any):
            return httpx.Response(
                200,
                json={"error": {"message": ERROR_MSG, "type": "api_error"}},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(ns, "_http_client", _Client())
    backend = SimpleNamespace(
        id="b0", type="omlx", chat_url="http://omlx/v1/chat/completions",
        models=["m"], resolve_model=lambda h: h,
    )  # fmt: skip
    tried: dict[tuple[str, str], str] = {}

    result = await ns._try_non_streaming(
        backend, {"messages": []}, ws, 0.0, persona="", tried=tried
    )

    assert result is None  # no 200 completion with no choices
    assert recorded == [(ws, "backend_in_band_error")]
    assert ERROR_MSG in next(iter(tried.values()))
