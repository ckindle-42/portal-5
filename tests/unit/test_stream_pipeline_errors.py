"""A Pipeline stream error has two audiences and must not confuse them.

Handed to ``_stream_with_fallback`` it is the ``data: {"error": ...}`` envelope the
wrapper cascades on, so the user still gets an answer from the next candidate. It
is only the *final* emission to the client — the wrapper with its chain exhausted,
output already started, or a standalone single-candidate stream — that must end
well-formed: the error as content, one ``finish_reason``, one ``[DONE]``. A bare
``data: {"error": ...}`` frame is rejected by opencode as "Invalid
openai-compatible-chat stream event" and kills the session — seen live on an oMLX
streaming hop whose model had not produced a token yet (2026-10-21, 15:2x).
"""

from __future__ import annotations

import json
import typing
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.responses import JSONResponse

import portal.platform.inference.router.backend_introspect as bi
import portal.platform.inference.router.streaming as st
from portal.platform.inference.router.correlation import set_correlation_id

DONE = b"data: [DONE]\n\n"
TIMEOUT_MSG = "Response timed out — model may still be generating. Please retry."
NO_MODEL_MSG = "Backend timed out and no model is loaded. Please retry."
TOOLS = [{"type": "function", "function": {"name": "write", "parameters": {}}}]
FINISH_TOOL_CALLS = json.dumps(
    {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}
)


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


class _RespThenRaise(_Resp):
    """A 200 stream that dies partway through — output already reached the client."""

    def __init__(self, lines: list[str], exc: Exception) -> None:
        super().__init__(lines)
        self._exc = exc

    async def aiter_lines(self) -> typing.AsyncIterator[str]:
        for line in self._lines:
            yield line
        raise self._exc


class _Ctx:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _Resp:
        return self._resp

    async def __aexit__(self, *_: typing.Any) -> None:
        return None


@pytest.fixture(autouse=True)
def _correlation_id() -> typing.Iterator[None]:
    set_correlation_id("corr-pipeline-error-test")
    yield
    set_correlation_id("")


@pytest.fixture
def stream_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr(st, "_http_client", client)
    return client


def _serve(client: MagicMock, *responses: _Resp) -> None:
    queue = list(responses)
    client.stream.side_effect = lambda *_a, **_k: _Ctx(queue.pop(0))


def _fail_with(client: MagicMock, exc: Exception) -> None:
    client.stream.side_effect = exc


async def _drain(gen: typing.AsyncIterator[bytes]) -> list[bytes]:
    return [c async for c in gen]


def _payloads(chunks: list[bytes]) -> list[dict[str, typing.Any]]:
    """Every frame the client parses as a chat chunk; a bare error frame fails here."""
    out: list[dict[str, typing.Any]] = []
    for chunk in chunks:
        for line in chunk.decode().splitlines():
            if not line.startswith("data: "):
                continue
            body = line[6:].strip()
            if body == "[DONE]":
                continue
            payload = json.loads(body)
            assert "choices" in payload, f"non-chat event reached the client: {payload}"
            out.append(payload)
    return out


def _assert_terminal(chunks: list[bytes], message: str) -> None:
    """One finish_reason, one [DONE], and the error visible as answer content."""
    content = "".join(
        (choice.get("delta") or {}).get("content") or ""
        for payload in _payloads(chunks)
        for choice in payload["choices"]
    )
    assert message in content
    reasons = [
        choice["finish_reason"]
        for payload in _payloads(chunks)
        for choice in payload["choices"]
        if choice.get("finish_reason")
    ]
    assert reasons == ["stop"]
    assert chunks.count(DONE) == 1
    assert chunks[-1] == DONE


def _assert_well_formed(chunks: list[bytes]) -> None:
    """One finish_reason and one trailing [DONE] — a client can read the end."""
    reasons = [
        choice["finish_reason"]
        for payload in _payloads(chunks)
        for choice in payload["choices"]
        if choice.get("finish_reason")
    ]
    assert reasons == ["stop"]
    assert chunks.count(DONE) == 1
    assert chunks[-1] == DONE


def _record_errors(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(st, "_record_error", lambda ws, kind: recorded.append((ws, kind)))
    return recorded


# ── tool loop (streaming.py:1017, 1027, 1034, 1209) ──────────────────


@pytest.mark.anyio
@pytest.mark.parametrize("still_running", [True, False], ids=["busy", "no-model"])
async def test_tool_loop_timeout_ends_well_formed(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch, still_running: bool
) -> None:
    recorded = _record_errors(monkeypatch)
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(still_running))
    _fail_with(stream_client, httpx.ReadTimeout("idle 600s"))
    body = {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS}

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://omlx/v1/chat/completions", body, "ws", "m", "p", {"write"}
        )
    )

    _assert_terminal(chunks, TIMEOUT_MSG if still_running else NO_MODEL_MSG)
    assert recorded == ([] if still_running else [("ws", "stream_timeout")])


@pytest.mark.anyio
async def test_tool_loop_stream_error_ends_well_formed(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _record_errors(monkeypatch)
    _fail_with(stream_client, RuntimeError("connection reset"))
    body = {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS}

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://omlx/v1/chat/completions", body, "ws", "m", "p", {"write"}
        )
    )

    _assert_terminal(chunks, "Backend connection error")
    assert recorded == [("ws", "stream_error")]


@pytest.mark.anyio
async def test_tool_call_parse_failure_ends_well_formed(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _record_errors(monkeypatch)
    _serve(stream_client, _Resp([f"data: {FINISH_TOOL_CALLS}", "data: [DONE]"]))
    body = {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS}

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://omlx/v1/chat/completions", body, "ws", "m", "p", {"write"}
        )
    )

    _assert_terminal(chunks, "Tool call could not be parsed from the model response")
    assert recorded == [("ws", "tool_parse_failure")]


# ── plain path (streaming.py:1473, 1694, 1708, 1719) ─────────────────


@pytest.mark.anyio
async def test_pipeline_not_ready_ends_well_formed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st, "_http_client", None)

    chunks = await _drain(
        st._stream_from_backend_guarded("http://x/v1/chat/completions", {}, "ws", "m")
    )

    _assert_terminal(chunks, "Pipeline not ready")


@pytest.mark.anyio
@pytest.mark.parametrize("still_running", [True, False], ids=["busy", "no-model"])
async def test_guarded_timeout_ends_well_formed(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch, still_running: bool
) -> None:
    recorded = _record_errors(monkeypatch)
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(still_running))
    _fail_with(stream_client, httpx.ReadTimeout("idle 600s"))

    chunks = await _drain(
        st._stream_from_backend_guarded("http://omlx/v1/chat/completions", {}, "ws", "m")
    )

    _assert_terminal(chunks, TIMEOUT_MSG if still_running else NO_MODEL_MSG)
    assert recorded == ([] if still_running else [("ws", "stream_timeout")])


@pytest.mark.anyio
async def test_guarded_stream_error_ends_well_formed(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _record_errors(monkeypatch)
    _fail_with(stream_client, RuntimeError("connection reset"))

    chunks = await _drain(
        st._stream_from_backend_guarded("http://omlx/v1/chat/completions", {}, "ws", "m")
    )

    _assert_terminal(chunks, "Backend connection error — check server logs")
    assert recorded == [("ws", "stream_error")]


# ── fallback wrapper (streaming.py:2467, 2515) ───────────────────────


def _backend(bid: str = "b0") -> typing.Any:
    return SimpleNamespace(
        id=bid, type="ollama", chat_url="http://engine/v1/chat/completions", models=["m"]
    )


async def _wrapper_run(
    monkeypatch: pytest.MonkeyPatch,
    inner_chunks: list[bytes] | None,
    *,
    raises: Exception | None = None,
    remaining: list[typing.Any] | None = None,
) -> tuple[list[bytes], list[str]]:
    calls: list[str] = []

    async def inner(*_a: typing.Any, **_k: typing.Any) -> typing.AsyncIterator[bytes]:
        if raises is not None:
            raise raises
        for chunk in inner_chunks or []:
            yield chunk

    async def fake_ns(backend: typing.Any, *_a: typing.Any, **_k: typing.Any) -> None:
        calls.append(backend.id)
        return None

    monkeypatch.setattr(st, "_select_stream_fn", lambda *a, **k: inner())
    monkeypatch.setattr(st, "_try_non_streaming", fake_ns)
    gen = st._stream_with_fallback(
        backend=_backend(),
        body={},
        workspace_id="ws",
        target_model="m",
        persona="p",
        effective_tools=[],
        start_time=0.0,
        has_tools=False,
        chain=[],
        portal_no_tools=False,
        secondary_model="",
        tertiary_model="",
        remaining=remaining or [],
        slot=MagicMock(),
        backend_body={},
    )
    return await _drain(gen), calls


@pytest.mark.anyio
async def test_fallback_wrapper_after_output_ends_well_formed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _record_errors(monkeypatch)
    inner = [
        b'data: {"choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": null}]}\n\n',
        st._backend_error_chunk(500, b"upstream exploded"),
        DONE,
    ]

    chunks, calls = await _wrapper_run(monkeypatch, inner, remaining=[_backend("b1")])

    assert calls == []  # output already on screen: no second answer appended
    _assert_terminal(chunks, "Backend returned HTTP 500: upstream exploded")
    assert recorded == [("ws", "stream_failed_after_output")]


@pytest.mark.anyio
async def test_fallback_wrapper_all_backends_failed_ends_well_formed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _record_errors(monkeypatch)
    inner = [st._backend_error_chunk(503, b"engine down"), DONE]

    chunks, _ = await _wrapper_run(monkeypatch, inner)

    _assert_terminal(chunks, "Backend returned HTTP 503: engine down")
    assert recorded == [("ws", "all_backends_failed")]


@pytest.mark.anyio
async def test_fallback_wrapper_exception_without_buffer_ends_well_formed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _record_errors(monkeypatch)

    chunks, _ = await _wrapper_run(monkeypatch, None, raises=RuntimeError("boom"))

    _assert_terminal(chunks, "All backends failed")
    assert recorded == [("ws", "all_backends_failed")]


# ── the fallback cascade the wrapper must still see ──────────────────


def _content(chunks: list[bytes]) -> str:
    return "".join(
        (choice.get("delta") or {}).get("content") or ""
        for payload in _payloads(chunks)
        for choice in payload["choices"]
    )


def _candidate_two(text: str = "candidate two answer") -> JSONResponse:
    return JSONResponse(
        {"choices": [{"message": {"role": "assistant", "content": text}}]},
        headers={"x-portal-route": "ws;b1;m"},
    )


def _guarded_inner() -> typing.AsyncIterator[bytes]:
    return st._stream_from_backend_guarded("http://omlx/v1/chat/completions", {}, "ws", "m")


async def _wrapped_run(
    monkeypatch: pytest.MonkeyPatch,
    inner: typing.Callable[[], typing.AsyncIterator[bytes]],
    *,
    remaining: list[typing.Any],
    body: dict[str, typing.Any] | None = None,
    tools: bool = False,
) -> tuple[list[bytes], list[str]]:
    """Drive the real wrapper over a real inner stream; candidate 2 answers non-streaming."""
    calls: list[str] = []

    async def fake_ns(backend: typing.Any, *_a: typing.Any, **_k: typing.Any) -> JSONResponse:
        calls.append(backend.id)
        return _candidate_two()

    monkeypatch.setattr(st, "_select_stream_fn", lambda *_a, **_k: inner())
    monkeypatch.setattr(st, "_try_non_streaming", fake_ns)
    gen = st._stream_with_fallback(
        backend=_backend("b0"),
        body={} if body is None else body,
        workspace_id="ws",
        target_model="m",
        persona="p",
        effective_tools=["write"] if tools else [],
        start_time=0.0,
        has_tools=tools,
        chain=[],
        portal_no_tools=False,
        secondary_model="",
        tertiary_model="",
        remaining=remaining,
        slot=MagicMock(),
        backend_body={} if body is None else body,
    )
    return await _drain(gen), calls


@pytest.mark.anyio
async def test_timeout_before_first_token_cascades_to_next_candidate(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(False))
    _record_errors(monkeypatch)
    _fail_with(stream_client, httpx.ReadTimeout("idle 600s"))

    chunks, calls = await _wrapped_run(monkeypatch, _guarded_inner, remaining=[_backend("b1")])

    assert calls == ["b1"]
    _assert_well_formed(chunks)
    assert _content(chunks) == "candidate two answer"
    assert NO_MODEL_MSG not in _content(chunks)


@pytest.mark.anyio
async def test_stream_error_before_first_token_cascades_to_next_candidate(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_errors(monkeypatch)
    _fail_with(stream_client, RuntimeError("connection reset"))

    chunks, calls = await _wrapped_run(monkeypatch, _guarded_inner, remaining=[_backend("b1")])

    assert calls == ["b1"]
    _assert_well_formed(chunks)
    assert _content(chunks) == "candidate two answer"
    assert "Backend connection error" not in _content(chunks)


@pytest.mark.anyio
async def test_tool_parse_failure_before_output_cascades_to_next_candidate(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _record_errors(monkeypatch)
    _serve(stream_client, _Resp([f"data: {FINISH_TOOL_CALLS}", "data: [DONE]"]))
    body = {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS}

    def inner() -> typing.AsyncIterator[bytes]:
        return st._stream_with_tool_loop_impl(
            "http://omlx/v1/chat/completions", body, "ws", "m", "p", {"write"}
        )

    chunks, calls = await _wrapped_run(
        monkeypatch, inner, remaining=[_backend("b1")], body=body, tools=True
    )

    assert calls == ["b1"]
    assert ("ws", "tool_parse_failure") in recorded
    _assert_well_formed(chunks)
    assert _content(chunks) == "candidate two answer"


@pytest.mark.anyio
async def test_exhausted_chain_ends_with_one_terminal_frame(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(False))
    recorded = _record_errors(monkeypatch)
    _fail_with(stream_client, httpx.ReadTimeout("idle 600s"))

    chunks, calls = await _wrapped_run(monkeypatch, _guarded_inner, remaining=[])

    assert calls == []
    _assert_terminal(chunks, NO_MODEL_MSG)
    assert recorded == [("ws", "stream_timeout"), ("ws", "all_backends_failed")]


@pytest.mark.anyio
async def test_error_after_output_started_ends_well_formed_without_cascade(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(True))
    recorded = _record_errors(monkeypatch)
    partial = (
        'data: {"choices": [{"index": 0, "delta": {"content": "partial answer"}, '
        '"finish_reason": null}]}'
    )
    _serve(stream_client, _RespThenRaise([partial], httpx.ReadTimeout("idle 600s")))

    chunks, calls = await _wrapped_run(monkeypatch, _guarded_inner, remaining=[_backend("b1")])

    assert calls == []  # a second answer must not be appended to the partial one
    assert "partial answer" in _content(chunks)
    _assert_terminal(chunks, TIMEOUT_MSG)
    assert recorded == [("ws", "stream_failed_after_output")]


# ── the shared helper ────────────────────────────────────────────────


def test_in_band_frames_share_the_terminal_framing() -> None:
    frames = st._in_band_error_frames("rid", "ws", "m", "backend said no")

    assert frames == [
        st._content_chunk("rid", "ws", f"{st._IN_BAND_ERROR_NOTICE}backend said no]"),
        st._completion_finish_chunk("stop"),
        DONE,
    ]
    assert st._error_terminal_frames("rid", "ws", "boom")[0] == st._content_chunk(
        "rid", "ws", f"{st._PIPELINE_ERROR_NOTICE}boom]"
    )


async def _async(value: typing.Any) -> typing.Any:
    return value
