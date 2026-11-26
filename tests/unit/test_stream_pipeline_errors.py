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

import asyncio
import json
import os
import subprocess
import time
import typing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.responses import JSONResponse

import portal.platform.inference.router.backend_introspect as bi
import portal.platform.inference.router.handlers as handlers
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


@pytest.mark.anyio
async def test_turn_deadline_closes_stalled_stream_and_records_reason(monkeypatch) -> None:
    closed = False
    notes: list[dict[str, typing.Any]] = []
    spans: list[tuple[str, dict[str, typing.Any]]] = []

    async def stalled() -> typing.AsyncIterator[bytes]:
        nonlocal closed
        try:
            yield b": first byte\n\n"
            await asyncio.Event().wait()
        finally:
            closed = True

    async def no_room(*_args: typing.Any, **_kwargs: typing.Any) -> None:
        return None

    monkeypatch.setattr(handlers, "trace_note", lambda **fields: notes.append(fields))
    monkeypatch.setattr(handlers, "trace_span", lambda name, **fields: spans.append((name, fields)))
    monkeypatch.setattr(handlers, "finalize_trace", lambda: None)
    monkeypatch.setattr(st, "make_room_for_omlx", no_room)
    monkeypatch.setattr(st, "_select_stream_fn", lambda *_args, **_kwargs: stalled())

    chunks = await _drain(
        handlers._with_portal_timings(
            st._stream_with_fallback(
                backend=_backend(),
                body={},
                workspace_id="auto-coding",
                target_model="qwen",
                persona="auto",
                effective_tools=[],
                start_time=time.monotonic(),
                has_tools=False,
                chain=[],
                portal_no_tools=False,
                secondary_model="",
                tertiary_model="",
                remaining=[],
                slot=MagicMock(),
                backend_body={},
            ),
            workspace_id="auto-coding",
            start_time=time.monotonic(),
            timeout_s=0.01,
        )
    )

    _assert_terminal(chunks, "turn deadline")
    assert closed
    assert any(
        note.get("outcome") == "timeout" and note.get("turn_end_reason") == "request_timeout"
        for note in notes
    )
    assert ("stream.deadline", {"reason": "request_timeout", "timeout_s": 0.01}) in spans


@pytest.mark.anyio
async def test_turn_deadline_resets_after_each_active_chunk(monkeypatch) -> None:
    _silence_trace(monkeypatch)

    async def active() -> typing.AsyncIterator[bytes]:
        for _ in range(4):
            await asyncio.sleep(0.02)
            yield b'data: {"choices":[{"delta":{"content":"active"}}]}\n\n'
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        yield DONE

    chunks = await _drain(
        handlers._with_portal_timings(
            active(),
            workspace_id="auto-coding",
            start_time=time.monotonic(),
            timeout_s=0.03,
        )
    )

    _assert_well_formed(chunks)
    assert b"".join(chunks).count(b'content":"active"') == 4


@pytest.mark.anyio
async def test_turn_deadline_keeps_absolute_ceiling(monkeypatch) -> None:
    closed = False
    spans: list[tuple[str, dict[str, typing.Any]]] = []

    async def active() -> typing.AsyncIterator[bytes]:
        nonlocal closed
        try:
            while True:
                await asyncio.sleep(0.04)
                yield b'data: {"choices":[{"delta":{"content":"active"}}]}\n\n'
        finally:
            closed = True

    monkeypatch.setattr(handlers, "_MAX_STREAM_DURATION_S", 0.18)
    monkeypatch.setattr(handlers, "trace_note", lambda **_fields: None)
    monkeypatch.setattr(handlers, "trace_span", lambda name, **fields: spans.append((name, fields)))
    monkeypatch.setattr(handlers, "finalize_trace", lambda: None)

    chunks = await _drain(
        handlers._with_portal_timings(
            active(),
            workspace_id="auto-coding",
            start_time=time.monotonic(),
            timeout_s=0.1,
        )
    )

    _assert_terminal(chunks, "turn deadline")
    assert closed
    assert ("stream.deadline", {"reason": "request_timeout", "timeout_s": 0.18}) in spans


@pytest.mark.anyio
async def test_turn_deadline_stops_after_backend_terminal_marker(monkeypatch) -> None:
    closed = False
    deadlines: list[dict[str, typing.Any]] = []

    async def done_then_stall() -> typing.AsyncIterator[bytes]:
        nonlocal closed
        try:
            yield b'data: {"choices":[{"finish_reason":"stop"}]}\n\n'
            yield DONE
            await asyncio.Event().wait()
        finally:
            closed = True

    monkeypatch.setattr(handlers, "trace_span", lambda _name, **fields: deadlines.append(fields))
    monkeypatch.setattr(handlers, "finalize_trace", lambda: None)

    chunks = await _drain(
        handlers._with_portal_timings(
            done_then_stall(),
            workspace_id="auto-coding",
            start_time=time.monotonic(),
            timeout_s=0.01,
        )
    )

    _assert_well_formed(chunks)
    assert chunks.count(DONE) == 1
    assert closed
    assert not deadlines


def _silence_trace(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, typing.Any]]:
    notes: list[dict[str, typing.Any]] = []
    monkeypatch.setattr(handlers, "trace_note", lambda **fields: notes.append(fields))
    monkeypatch.setattr(handlers, "trace_span", lambda *_a, **_k: None)
    monkeypatch.setattr(handlers, "finalize_trace", lambda: None)
    return notes


@pytest.mark.anyio
async def test_stream_that_ends_without_done_still_terminates(monkeypatch) -> None:
    """A backend that closes after tokens, the cold-start miss, still ends the SSE."""
    _silence_trace(monkeypatch)

    async def closed_early() -> typing.AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"PONG"}}]}\n\n'

    chunks = await _drain(handlers._with_portal_timings(closed_early(), workspace_id="auto-daily"))

    assert b"PONG" in b"".join(chunks)
    assert chunks.count(DONE) == 1
    assert chunks[-1] == DONE


@pytest.mark.anyio
async def test_exception_after_preamble_ends_with_done(monkeypatch) -> None:
    """A 5xx/reset after the role chunk must not drop the socket without [DONE]."""
    notes = _silence_trace(monkeypatch)

    async def reset() -> typing.AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"role":"assistant","content":""}}]}\n\n'
        raise RuntimeError("connection reset")

    chunks = await _drain(handlers._with_portal_timings(reset(), workspace_id="auto-daily"))

    _assert_terminal(chunks, "stream failed")
    assert any(note.get("turn_end_reason") == "stream_error" for note in notes)


@pytest.mark.anyio
async def test_client_disconnect_during_cold_load_ends_with_done(monkeypatch) -> None:
    """Cancel at the load wait, after the preamble, still writes the terminal frame."""
    notes = _silence_trace(monkeypatch)

    async def cold_load() -> typing.AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"role":"assistant","content":""}}]}\n\n'
        await asyncio.Event().wait()

    agen = handlers._with_portal_timings(
        cold_load(), workspace_id="auto-daily", start_time=time.monotonic(), timeout_s=30
    )
    chunks: list[bytes] = []

    async def consume() -> None:
        async for chunk in agen:
            chunks.append(chunk)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.wait_for(task, timeout=2)

    _assert_terminal(chunks, "client disconnected")
    assert any(note.get("turn_end_reason") == "client_disconnect" for note in notes)


def test_cold_stream_smoke_timeout_exceeds_pipeline_stream_ceiling(tmp_path: Path) -> None:
    script = Path(__file__).parents[2] / "scripts/smoke_stream.sh"
    text = script.read_text()
    timeout_line = next(line for line in text.splitlines() if line.startswith("TIMEOUT="))
    smoke_timeout_s = int(timeout_line.partition(":-")[2].partition("}")[0])
    curl_stub = tmp_path / "curl"
    curl_stub.write_text(
        """#!/bin/sh
output=
timeout=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o) output="$2"; shift 2 ;;
        --max-time) timeout="$2"; shift 2 ;;
        -w) shift 2 ;;
        *) shift ;;
    esac
done
if [ "$timeout" -le __SERVER_CEILING__ ]; then
    printf 'data: {"choices":[{"delta":{"content":"PONG"}}]}\\n\\n' > "$output"
    printf 200
    exit 28
fi
printf 'data: {"choices":[{"delta":{"content":"PONG"}}]}\\n\\ndata: [DONE]\\n\\n' > "$output"
printf 200
""".replace("__SERVER_CEILING__", str(int(handlers._MAX_STREAM_DURATION_S))),
        encoding="utf-8",
    )
    curl_stub.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env.pop("SMOKE_STREAM_TIMEOUT", None)

    assert '--max-time "$TIMEOUT"' in text
    assert smoke_timeout_s > handlers._MAX_STREAM_DURATION_S

    interrupted = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        check=False,
        env={**env, "SMOKE_STREAM_TIMEOUT": "30"},
        text=True,
        timeout=3,
    )
    assert interrupted.returncode == 1
    assert "hit its external 30s safety ceiling" in interrupted.stdout

    completed = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=3,
    )
    assert completed.returncode == 0, completed.stdout
    assert "[DONE] received" in completed.stdout


@pytest.mark.anyio
async def test_backend_507_through_timings_ends_with_done(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A load-guard refusal is a finished stream, including the timings wrapper."""
    _silence_trace(monkeypatch)
    monkeypatch.setattr(st.no_answer, "chat_ui", lambda: False)
    _serve(
        stream_client,
        _Resp([], status=507, body=b'{"error":"cannot load model"}'),
    )

    chunks = await _drain(
        handlers._with_portal_timings(
            st._stream_from_backend_guarded("http://ollama/v1/chat/completions", {}, "ws", "m"),
            workspace_id="ws",
        )
    )

    assert chunks.count(DONE) == 1
    assert chunks[-1] == DONE
    assert b"cannot load model" in b"".join(chunks)


@pytest.mark.anyio
async def test_guarded_stream_without_backend_done_is_not_success(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _record_errors(monkeypatch)
    _serve(stream_client, _Resp([f"data: {SERVED}"]))

    chunks = await _drain(
        st._stream_from_backend_guarded("http://omlx/v1/chat/completions", {}, "ws", "m")
    )

    assert "served" in _content(chunks)
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
async def test_client_tools_only_inband_error_before_output_cascades_to_candidate(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _record_errors(monkeypatch)
    body = {
        "messages": [{"role": "user", "content": "lookup"}],
        "tools": [{"type": "function", "function": {"name": "client_lookup", "parameters": {}}}],
    }
    tool_call = {
        "choices": [
            {
                "index": 0,
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-client-lookup",
                            "type": "function",
                            "function": {"name": "client_lookup", "arguments": "{}"},
                        }
                    ]
                },
                "finish_reason": None,
            }
        ]
    }
    _serve(
        stream_client,
        _Resp(
            [
                f"data: {json.dumps(tool_call)}",
                'data: {"error":{"message":"tool parser aborted"}}',
            ]
        ),
    )

    def inner() -> typing.AsyncIterator[bytes]:
        return st._stream_with_tool_loop_impl(
            "http://engine/v1/chat/completions", body, "ws", "m", "p", set()
        )

    chunks, calls = await _wrapped_run(
        monkeypatch, inner, remaining=[_backend("b1")], body=body, tools=True
    )

    assert calls == ["b1"]
    assert recorded == [("ws", "backend_in_band_error")]
    _assert_well_formed(chunks)
    assert _content(chunks) == "candidate two answer"


@pytest.mark.anyio
@pytest.mark.parametrize("client_tools_only", [False, True], ids=["plain", "client-tools-only"])
async def test_single_candidate_http_error_ends_with_valid_chat_frames(
    stream_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    client_tools_only: bool,
) -> None:
    _record_errors(monkeypatch)
    _serve(stream_client, _Resp([], status=400, body=b'{"error":"invalid request"}'))
    body = {"messages": [{"role": "user", "content": "edit"}]}
    if client_tools_only:
        body["tools"] = TOOLS
    backend = _backend()
    backend.chat_url = "http://engine/v1/chat/completions"
    stream = st._select_stream_fn(
        backend,
        body,
        MagicMock(),
        "ws",
        "m",
        "p",
        [],
        None,
        [],
        "",
        "",
        False,
        client_tools_only,
    )

    chunks = await _drain(stream)

    payloads = _payloads(chunks)
    finishes = [
        choice.get("finish_reason")
        for payload in payloads
        for choice in payload.get("choices", [])
        if choice.get("finish_reason") is not None
    ]
    assert finishes == ["stop"]
    assert chunks.count(DONE) == 1
    assert chunks[-1] == DONE
    assert "Backend returned HTTP 400: invalid request" in _content(chunks)


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


def _cap_fallback_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A chat-UI audience whose lighter declared variant serves the turn."""
    from portal.platform.inference import load_guard
    from portal.platform.inference.router import capacity_fallback as cf
    from portal.platform.inference.router import no_answer, validation
    from portal.platform.inference.router.workspaces import WORKSPACES

    # A leaked GUARD from another test would have _seat_fits probe the fake URL.
    monkeypatch.setattr(load_guard, "GUARD", None)
    monkeypatch.setattr(no_answer, "chat_ui", lambda: True)
    fallback_backend = SimpleNamespace(
        id="fake",
        type="ollama",
        group="general",
        url="http://engine",
        chat_url="http://engine/v1/chat/completions",
        models=["lite-hint"],
        resolve_model=lambda hint: hint,
    )
    monkeypatch.setattr(
        validation,
        "registry",
        SimpleNamespace(
            list_backends=lambda: [fallback_backend],
            get_backend_candidates=lambda _ws: [fallback_backend],
            declared_groups=lambda _ws: ["general"],
        ),
    )
    monkeypatch.setattr(cf, "_variant_names", lambda _ws: ["lite"])
    monkeypatch.setattr(cf, "_register_variant", lambda _base, _name: "ws::lite")
    monkeypatch.setitem(WORKSPACES, "ws::lite", {"model_hint": "lite-hint"})

    async def fallback_dispatch(_backend: typing.Any, *_a: typing.Any, **_k: typing.Any):
        return JSONResponse(
            {"choices": [{"message": {"role": "assistant", "content": "lite answer"}}]},
            headers={"x-portal-route": "ws::lite;fake;lite-hint"},
        )

    monkeypatch.setattr(st, "_try_non_streaming", fallback_dispatch)


def _capacity_error_stream() -> typing.Callable[[], typing.AsyncIterator[bytes]]:
    async def inner() -> typing.AsyncIterator[bytes]:
        yield (
            b'data: {"error": "Cannot load m: projected memory 32.8 GiB would exceed '
            b'host headroom", "status": 507}\n\n'
        )

    return inner


@pytest.mark.anyio
async def test_capacity_fallback_receipt_survives_the_error_stamp(
    stream_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: typing.Any,
) -> None:
    """A chat turn a lighter variant served must not record outcome="error".

    The wrapper stamps "error" when its candidate ladder is exhausted; the capacity
    fallback that then answers the chat UI overwrites the record with the seat that
    actually answered (try_capacity_fallback). The stamps are therefore applied
    before _exhausted_frames runs, not after (2026-11-25 review).
    """
    from portal.platform.inference.router import trace

    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path))
    _cap_fallback_env(monkeypatch)
    recorded = _record_errors(monkeypatch)
    trace.start_trace("p5-captest")
    try:
        monkeypatch.setattr(st, "_select_stream_fn", lambda *_a, **_k: _capacity_error_stream()())
        chunks = await _drain(
            st._stream_with_fallback(
                backend=_backend("b0"),
                body={"messages": [{"role": "user", "content": "hi"}]},
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
                remaining=[],
                slot=MagicMock(),
                backend_body={"messages": [{"role": "user", "content": "hi"}]},
            )
        )

        assert recorded == [("ws", "all_backends_failed")]
        assert _assert_well_formed(chunks) is None
        assert "lite answer" in _content(chunks)
        record = trace.current_trace().to_dict()
        assert record["outcome"] == "ok"
        assert record["backend"] == "fake" and record["model"] == "lite-hint"
        assert record["workspace"] == "ws::lite" and record["capacity_fallback"] == "lite"
    finally:
        trace._current.set(None)


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


# ── a chain's own hops are a fallback cascade ────────────────────────


def _delta(text: str) -> str:
    frame = {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
    return f"data: {json.dumps(frame)}"


def _serve_sequence(client: MagicMock, *items: typing.Any) -> None:
    """Serve a response, or raise an exception, per call — in order."""
    queue = list(items)

    def _next(*_a: typing.Any, **_k: typing.Any) -> _Ctx:
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Ctx(item)

    client.stream.side_effect = _next


_BLUE_HOP = {"model": "blue", "system": "defend", "user_template": "{hop_0}"}


def _chain_gen(chain: list[dict[str, typing.Any]]) -> typing.AsyncIterator[bytes]:
    """One single-candidate streaming request whose workspace has a multi-hop chain."""
    return st._stream_with_chain(
        "http://engine/v1/chat/completions",
        {"messages": [{"role": "user", "content": "question"}]},
        MagicMock(),
        workspace_id="ws",
        primary_model="red",
        chain=chain,
        start_time=None,
        persona="p",
    )


@pytest.mark.anyio
async def test_failed_chain_hop_stops_before_the_next_stage(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(False))
    _record_errors(monkeypatch)
    monkeypatch.setattr(st, "resolve_hop_target", lambda _ws, _m, url, body: (url, body))
    _serve_sequence(stream_client, httpx.ReadTimeout("idle 600s"))

    chunks = await _drain(_chain_gen([dict(_BLUE_HOP, label="BLUE TEAM")]))

    assert stream_client.stream.call_count == 1
    _assert_terminal(chunks, NO_MODEL_MSG)


@pytest.mark.anyio
async def test_failed_intermediate_prefill_hop_uses_candidate_fallback(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(False))
    monkeypatch.setattr(st, "resolve_hop_target", lambda _ws, _m, url, body: (url, body))
    monkeypatch.setattr(st, "make_room_for_omlx", lambda *_a, **_k: _async(None))
    _record_errors(monkeypatch)
    _serve_sequence(
        stream_client,
        _Resp(
            [],
            status=400,
            body=b'{"error":{"message":"prefill memory guard: would exceed the memory ceiling"}}',
        ),
        _Resp([_delta("later chain answer from empty hop_0"), "data: [DONE]"]),
    )

    def inner() -> typing.AsyncIterator[bytes]:
        return _chain_gen([dict(_BLUE_HOP, label="BLUE TEAM")])

    chunks, calls = await _wrapped_run(
        monkeypatch,
        inner,
        remaining=[_backend("b1")],
        body={"messages": [{"role": "user", "content": "question"}]},
    )

    assert stream_client.stream.call_count == 1
    assert calls == ["b1"]
    _assert_well_formed(chunks)
    assert _content(chunks) == "candidate two answer"


@pytest.mark.anyio
async def test_every_chain_hop_failing_ends_with_one_terminal_frame(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(False))
    _record_errors(monkeypatch)
    monkeypatch.setattr(st, "resolve_hop_target", lambda _ws, _m, url, body: (url, body))
    _serve_sequence(
        stream_client,
        _Resp([_delta("red analysis"), "data: [DONE]"]),
        httpx.ReadTimeout("idle 600s"),
    )

    chunks = await _drain(
        _chain_gen(
            [
                dict(_BLUE_HOP),
                {"model": "green", "system": "review", "user_template": "{hop_1}"},
            ]
        )
    )

    assert stream_client.stream.call_count == 2
    _assert_terminal(chunks, NO_MODEL_MSG)


@pytest.mark.anyio
async def test_exhausted_chain_cascades_to_the_next_candidate(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hops are tried first; the candidate fallback runs once every hop has failed."""
    monkeypatch.setattr(bi, "model_still_running", lambda *_a, **_k: _async(False))
    _record_errors(monkeypatch)
    monkeypatch.setattr(st, "resolve_hop_target", lambda _ws, _m, url, body: (url, body))
    _serve_sequence(stream_client, httpx.ReadTimeout("idle 600s"), httpx.ReadTimeout("idle 600s"))
    calls: list[str] = []

    async def fake_ns(backend: typing.Any, *_a: typing.Any, **_k: typing.Any) -> JSONResponse:
        calls.append(backend.id)
        return _candidate_two()

    monkeypatch.setattr(
        st, "_select_stream_fn", lambda *_a, **_k: _chain_gen([dict(_BLUE_HOP, label="BLUE TEAM")])
    )
    monkeypatch.setattr(st, "_try_non_streaming", fake_ns)
    gen = st._stream_with_fallback(
        backend=_backend("b0"),
        body={"messages": [{"role": "user", "content": "question"}]},
        workspace_id="ws",
        target_model="m",
        persona="p",
        effective_tools=[],
        start_time=0.0,
        has_tools=False,
        chain=[dict(_BLUE_HOP)],
        portal_no_tools=False,
        secondary_model="",
        tertiary_model="",
        remaining=[_backend("b1")],
        slot=MagicMock(),
        backend_body={"messages": [{"role": "user", "content": "question"}]},
    )

    chunks = await _drain(gen)

    assert calls == ["b1"]  # the hop separator is framing, not an answer on screen
    _assert_well_formed(chunks)
    assert "candidate two answer" in _content(chunks)
    assert NO_MODEL_MSG not in _content(chunks)


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


# ── the closing usage frame: an engine that reports nothing still ends a turn ──

ASK_USAGE = {"include_usage": True}


def _chunk(delta: dict[str, typing.Any], finish: str | None = None) -> str:
    payload = {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(payload)}"


def _usage_frame(completion: int) -> str:
    usage = {"prompt_tokens": 30, "completion_tokens": completion, "total_tokens": 30 + completion}
    return f"data: {json.dumps({'choices': [], 'usage': usage})}"


def _usages(chunks: list[bytes]) -> list[dict[str, typing.Any]]:
    return [p["usage"] for p in _payloads(chunks) if isinstance(p.get("usage"), dict)]


@pytest.mark.anyio
async def test_guarded_turn_the_engine_left_without_usage_ends_with_one(
    stream_client: MagicMock,
) -> None:
    _serve(stream_client, _Resp([_chunk({"content": "OK"}, "stop"), "data: [DONE]"]))
    body = {"messages": [{"role": "user", "content": "hi"}], "stream_options": ASK_USAGE}

    chunks = await _drain(
        st._stream_from_backend_guarded("http://ollama/v1/chat/completions", body, "ws", "m")
    )

    assert _usages(chunks) == [
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "source": "pipeline"}
    ]
    assert chunks[-1] == DONE and b"OK" in b"".join(chunks)


@pytest.mark.anyio
async def test_guarded_turn_keeps_the_engines_own_usage_unrepeated(
    stream_client: MagicMock,
) -> None:
    _serve(
        stream_client, _Resp([_chunk({"content": "OK"}, "stop"), _usage_frame(2), "data: [DONE]"])
    )
    body = {"messages": [{"role": "user", "content": "hi"}], "stream_options": ASK_USAGE}

    chunks = await _drain(
        st._stream_from_backend_guarded("http://ollama/v1/chat/completions", body, "ws", "m")
    )

    assert [u["completion_tokens"] for u in _usages(chunks)] == [2]
    assert chunks[-1] == DONE


@pytest.mark.anyio
async def test_tool_loop_turn_that_says_nothing_still_ends_with_usage(
    stream_client: MagicMock,
) -> None:
    """Live 2026-11-16, `auto` on nemotron: 0 content, 0 reasoning, no usage chunk."""
    _serve(stream_client, _Resp(["data: [DONE]"]))
    body = {
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "stream_options": ASK_USAGE,
    }

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://ollama/v1/chat/completions", body, "ws", "m", "p", set()
        )
    )

    content = "".join(
        (choice.get("delta") or {}).get("content") or ""
        for payload in _payloads(chunks)
        for choice in payload["choices"]
    )
    assert st.NO_ANSWER_MESSAGE in content
    assert _usages(chunks) == [
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "source": "pipeline"}
    ]
    assert chunks[-1] == DONE and chunks.count(DONE) == 1


@pytest.mark.anyio
async def test_tool_loop_reasoning_only_turn_reports_the_engines_usage(
    stream_client: MagicMock,
) -> None:
    """The same turn on a model that reasons: the engine's own count reaches the client."""
    _serve(
        stream_client,
        _Resp(
            [
                _chunk({"reasoning": "let me think"}),
                _chunk({}, "length"),
                _usage_frame(24),
                "data: [DONE]",
            ]
        ),
    )
    body = {
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "stream_options": ASK_USAGE,
    }

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://ollama/v1/chat/completions", body, "ws", "m", "p", set()
        )
    )

    assert [u["completion_tokens"] for u in _usages(chunks)] == [24]
    assert chunks[-1] == DONE and chunks.count(DONE) == 1


# ── oMLX aborts mid-prefill: free the idle residents and retry once ──
# 2026-11-19: the 2026-10-07 incident's exact failure — oMLX admitted the request
# (or had the seat resident), then the process-memory watermark killed it after
# the stream started, and the user got "[Pipeline stream error … aborted …]".

OMLX_ABORT = 'data: {"error": "oMLX memory guard aborted this request mid-prefill"}'
SERVED = json.dumps({"choices": [{"index": 0, "delta": {"content": "served"}}]})


def _freed_once(monkeypatch: pytest.MonkeyPatch, names: list[str] | None = None) -> list[int]:
    calls: list[int] = []

    async def fake_free() -> list[str]:
        calls.append(1)
        return ["nemotron"] if names is None else names

    monkeypatch.setattr(st, "free_ollama_for_omlx", fake_free)
    return calls


@pytest.mark.anyio
async def test_omlx_memory_abort_mid_prefill_frees_ollama_and_retries(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(st, "_backend_type_for_url", lambda _url: "omlx")
    freed = _freed_once(monkeypatch)
    _serve(stream_client, _Resp([OMLX_ABORT]), _Resp([f"data: {SERVED}", "data: [DONE]"]))

    chunks = await _drain(
        st._stream_from_backend_guarded(
            "http://omlx/v1/chat/completions", {"messages": []}, "ws", "m"
        )
    )

    assert freed == [1]
    assert stream_client.stream.call_count == 2
    assert _content(chunks) == "served"
    assert all(b'"error"' not in chunk for chunk in chunks)
    _assert_well_formed(chunks)


@pytest.mark.anyio
async def test_omlx_memory_abort_with_nothing_idle_still_ends_well_formed(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(st, "_backend_type_for_url", lambda _url: "omlx")
    freed = _freed_once(monkeypatch, names=[])
    _serve(stream_client, _Resp([OMLX_ABORT]))

    chunks = await _drain(
        st._stream_from_backend_guarded(
            "http://omlx/v1/chat/completions", {"messages": []}, "ws", "m"
        )
    )

    assert freed == [1]  # one attempt, then the error reaches the client
    assert stream_client.stream.call_count == 1
    _assert_terminal(chunks, "aborted this request mid-prefill")


@pytest.mark.anyio
async def test_omlx_memory_abort_after_output_is_never_retried(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(st, "_backend_type_for_url", lambda _url: "omlx")
    freed = _freed_once(monkeypatch)
    _serve(stream_client, _Resp([f"data: {SERVED}", OMLX_ABORT]))

    chunks = await _drain(
        st._stream_from_backend_guarded(
            "http://omlx/v1/chat/completions", {"messages": []}, "ws", "m"
        )
    )

    assert freed == []
    assert stream_client.stream.call_count == 1
    assert "served" in _content(chunks) and "mid-prefill" in _content(chunks)


@pytest.mark.anyio
async def test_tool_loop_omlx_memory_abort_mid_prefill_frees_and_retries_the_hop(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(st, "_backend_type_for_url", lambda _url: "omlx")
    freed = _freed_once(monkeypatch)
    body = {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS}
    _serve(
        stream_client,
        _Resp([OMLX_ABORT]),
        _Resp([f"data: {SERVED}", "data: [DONE]"]),
    )

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://omlx/v1/chat/completions", body, "ws", "m", "p", {"write"}
        )
    )

    assert freed == [1]
    assert stream_client.stream.call_count == 2
    assert "served" in _content(chunks)
    assert all(b'"error"' not in chunk for chunk in chunks)


@pytest.mark.anyio
async def test_multicandidate_omlx_capacity_retry_runs_once_before_fallback(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(st, "_backend_type_for_url", lambda _url: "omlx")

    async def no_room(_backend, _body):
        return None

    frees: list[int] = []

    async def fake_free() -> list[str]:
        frees.append(1)
        return ["idle-model"]

    monkeypatch.setattr(st, "make_room_for_omlx", no_room)
    monkeypatch.setattr(st, "free_ollama_for_omlx", fake_free)
    capacity = _Resp(
        [],
        status=507,
        body=b'{"error":"Cannot load m: projected memory would exceed host headroom"}',
    )
    _serve(stream_client, capacity, capacity)
    backend = SimpleNamespace(
        id="omlx-primary",
        type="omlx",
        chat_url="http://omlx/v1/chat/completions",
    )
    fallback_calls: list[str] = []

    async def fallback(candidate, *_args, **_kwargs):
        fallback_calls.append(candidate.id)
        return _candidate_two()

    monkeypatch.setattr(st, "_select_stream_fn", lambda *_args, **_kwargs: _guarded_inner())
    monkeypatch.setattr(st, "_try_non_streaming", fallback)
    chunks = await _drain(
        st._stream_with_fallback(
            backend=backend,
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
            remaining=[_backend("ollama-fallback")],
            slot=MagicMock(),
            backend_body={},
        )
    )

    assert stream_client.stream.call_count == 2
    assert frees == [1]
    assert fallback_calls == ["ollama-fallback"]
    assert _content(chunks) == "candidate two answer"


OMLX_INCOMPLETE_TOOL = (
    'data: {"error": {"message": "Model output contains an unrecoverable tool call. '
    'Previously delivered tool calls must not be executed again on retry.", '
    '"type": "server_error", "code": "incomplete_tool_call"}}'
)


@pytest.mark.anyio
async def test_tool_loop_omlx080_incomplete_tool_call_falls_through_to_rescue(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _record_errors(monkeypatch)
    _serve(stream_client, _Resp([OMLX_INCOMPLETE_TOOL]))

    async def _fake_rescue(*_args: object, **_kwargs: object) -> tuple[str, list[dict], str]:
        return "rescued answer", [], ""

    monkeypatch.setattr(st, "_rescue_empty_hop", _fake_rescue)
    body = {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS}

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://omlx/v1/chat/completions", body, "ws", "m", "p", {"write"}
        )
    )

    assert "rescued answer" in _content(chunks)
    assert ("ws", "unparsed_tool_call") in recorded
    assert ("ws", "backend_in_band_error") not in recorded


@pytest.mark.anyio
async def test_tool_loop_omlx080_incomplete_tool_call_after_output_still_aborts(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _record_errors(monkeypatch)
    _serve(stream_client, _Resp([f"data: {SERVED}", OMLX_INCOMPLETE_TOOL]))
    body = {"messages": [{"role": "user", "content": "edit"}], "tools": TOOLS}

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://omlx/v1/chat/completions", body, "ws", "m", "p", {"write"}
        )
    )

    assert "unrecoverable tool call" in _content(chunks)
    assert ("ws", "backend_in_band_error") in recorded
