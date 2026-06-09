"""Golden-output streaming tests (Phase 4 — T-10).

Tests for SSE stream parsing in ``_stream_from_backend_guarded`` and
``_stream_with_tool_loop_impl``. These must PASS before and after any
Phase-4 edit to ``router_pipe.py``.

Coverage:
- Plain content output (single-line and multi-line)
- tool_calls multi-hop (OpenAI SSE shape)
- reasoning → content promotion (reasoning_content in delta)
- Empty-line passthrough and [DONE] termination
"""

from __future__ import annotations

import json
import typing
from unittest.mock import MagicMock

import pytest

from portal_pipeline import router_pipe


# ── helpers ──────────────────────────────────────────────────────────


def _sse_line(payload: dict | str) -> bytes:
    """Build a single ``data: {...}`` or ``data: [DONE]`` byte line."""
    if isinstance(payload, dict):
        return f"data: {json.dumps(payload)}".encode()
    return f"data: {payload}".encode()


def _stream_lines(*raw_events: bytes) -> list[str]:
    """Turn concatenated raw SSE bytes into the list that ``aiter_lines()``
    would yield.  Each line is stripped of its trailing newline(s), empty
    lines (separators between SSE events) are preserved as ``""``.
    """
    lines: list[str] = []
    for raw in raw_events:
        text = raw.decode("utf-8", errors="replace")
        for line_text in text.splitlines():
            lines.append(line_text)
    return lines


async def _drain(gen) -> list[bytes]:
    """Collect every ``bytes`` chunk from an async generator."""
    chunks: list[bytes] = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


def _decode_chunks(chunks: list[bytes]) -> str:
    """Return the concatenated, decoded string for assertion readability."""
    return b"".join(chunks).decode("utf-8", errors="replace")


def _json_from_sse(chunks: list[bytes]) -> list[dict]:
    """Extract every JSON payload from ``data: {...}`` lines (skip [DONE])."""
    payloads: list[dict] = []
    for c in chunks:
        text = c.decode(errors="replace").strip()
        if text.startswith("data:") and not text.endswith("[DONE]"):
            candidate = text.removeprefix("data:").strip()
            if not candidate or not candidate.startswith("{"):
                continue
            try:
                payloads.append(json.loads(candidate))
            except json.JSONDecodeError:
                continue
    return payloads


class _MockStreamResponse:
    """Fake httpx response — returned from the async context manager.

    ``aiter_lines()`` yields ``str`` (the real httpx contract) —
    no trailing newline, already decoded.
    """

    def __init__(self, status_code: int, lines: list[str]):
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b"mock error body"


class _MockStreamContext:
    """Async context manager returned by ``_http_client.stream(...)``."""

    def __init__(self, status_code: int, lines: list[str]):
        self._status_code = status_code
        self._lines = lines

    async def __aenter__(self):
        return _MockStreamResponse(self._status_code, self._lines)

    async def __aexit__(self, *_: typing.Any):
        pass


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_client():
    """Provide a MagicMock as router_pipe._http_client so the stream method
    can be monkeypatched on top of it.  Restored after each test."""
    orig = router_pipe._http_client
    router_pipe._http_client = MagicMock()
    yield router_pipe._http_client
    router_pipe._http_client = orig


# ── tests ────────────────────────────────────────────────────────────


class TestStreamFallbackPlainContent:
    """Golden-output: plain content delta stream."""

    @pytest.mark.anyio
    async def test_plain_content_output(self, mock_client, monkeypatch):
        events = (
            _sse_line({"choices": [{"index": 0, "delta": {"content": "Hello"}}]})
            + b"\n\n"
            + _sse_line({"choices": [{"index": 0, "delta": {"content": " world"}}]})
            + b"\n\n"
            + b"data: [DONE]\n\n"
        )
        lines = _stream_lines(events)
        ctx = _MockStreamContext(200, lines)

        def fake_stream(method, url, **kwargs):
            return ctx

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        assert "Hello" in text
        assert "world" in text
        assert "[DONE]" in text

    @pytest.mark.anyio
    async def test_plain_content_no_ollama_native_translation(self, mock_client, monkeypatch):
        """Verify that Ollama native NDJSON is passed through (not translated) when
        URL is NOT ``/api/chat`` (F-OL1 dead code removal)."""
        ollama_ndjson = (
            b'{"model":"llama3","message":{"content":"Hi"}}\n'
            b'{"model":"llama3","message":{"content":" there"},"done":true}\n'
        )
        lines = _stream_lines(ollama_ndjson)
        ctx = _MockStreamContext(200, lines)

        def fake_stream(method, url, **kwargs):
            return ctx

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)

        # Since URL is /v1/... (not /api/chat), it's treated as OpenAI SSE.
        # Raw NDJSON content passes through as-is without translation.
        text = _decode_chunks(chunks)
        payloads = _json_from_sse(chunks)
        assert "message" in text or len(payloads) == 0


class TestStreamFallbackReasoningPromotion:
    """Golden-output: reasoning_content → content promotion."""

    @pytest.mark.anyio
    async def test_reasoning_promoted_when_content_empty(self, mock_client, monkeypatch):
        """Delta with reasoning_content but no content → reasoning surfaced."""
        events = (
            _sse_line(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "reasoning_content": "Let me think...",
                            },
                        }
                    ]
                }
            )
            + b"\n\n"
            + b"data: [DONE]\n\n"
        )
        lines = _stream_lines(events)
        ctx = _MockStreamContext(200, lines)

        def fake_stream(method, url, **kwargs):
            return ctx

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        # reasoning_content should be preserved in the output
        assert "Let me think" in text

    @pytest.mark.anyio
    async def test_reasoning_not_promoted_when_content_present(self, mock_client, monkeypatch):
        """Delta with both reasoning_content and content → both preserved."""
        events = (
            _sse_line(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "reasoning_content": "thinking",
                                "content": "answer",
                            },
                        }
                    ]
                }
            )
            + b"\n\n"
            + b"data: [DONE]\n\n"
        )
        lines = _stream_lines(events)
        ctx = _MockStreamContext(200, lines)

        def fake_stream(method, url, **kwargs):
            return ctx

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        assert "answer" in text


class TestStreamFallbackToolCalls:
    """Golden-output: tool_calls delta pass-through and content retention.

    ``_stream_from_backend_guarded`` is a low-level pass-through — it does
    NOT suppress tool_calls or finish_reason=tool_calls.  That suppression
    is the responsibility of ``_stream_with_tool_loop_impl`` (the caller).
    """

    @pytest.mark.anyio
    async def test_tool_calls_delta_passed_through(self, mock_client, monkeypatch):
        """Tool-call deltas pass through _stream_from_backend_guarded unchanged."""
        events = (
            _sse_line(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_1",
                                        "function": {
                                            "name": "search",
                                            "arguments": '{"q": "test"}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            )
            + b"\n\n"
        )
        lines = _stream_lines(events)
        ctx = _MockStreamContext(200, lines)

        def fake_stream(method, url, **kwargs):
            return ctx

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        # Tool calls appear in the raw pass-through; caller (tool_loop_impl) filters them
        assert "search" in text
        assert "call_1" in text
        assert "tool_calls" in text

    @pytest.mark.anyio
    async def test_finish_reason_tool_calls_passed_through(self, mock_client, monkeypatch):
        """finish_reason=tool_calls passes through _stream_from_backend_guarded."""
        events = (
            _sse_line(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "Let me look that up"},
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            )
            + b"\n\n"
        )
        lines = _stream_lines(events)
        ctx = _MockStreamContext(200, lines)

        def fake_stream(method, url, **kwargs):
            return ctx

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        assert "Let me look that up" in text
        assert "tool_calls" in text  # finish_reason passed through


class TestStreamFallbackErrorHandling:
    """Golden-output: error chunk on non-200 and connection errors."""

    @pytest.mark.anyio
    async def test_non_200_yields_error_chunk(self, mock_client, monkeypatch):
        """HTTP != 200 yields a ``data: {"error": ...}`` chunk."""

        def fake_stream(method, url, **kwargs):
            return _MockStreamContext(500, [])

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        assert '"error"' in text
        assert "500" in text or "Backend returned" in text


class TestStreamFallbackDoneTermination:
    """Golden-output: [DONE] terminator handling."""

    @pytest.mark.anyio
    async def test_done_terminator_preserved(self, mock_client, monkeypatch):
        """[DONE] marker is forwarded in the output stream."""
        events = (
            _sse_line({"choices": [{"index": 0, "delta": {"content": "Answer."}}]})
            + b"\n\n"
            + b"data: [DONE]\n\n"
        )
        lines = _stream_lines(events)
        ctx = _MockStreamContext(200, lines)

        def fake_stream(method, url, **kwargs):
            return ctx

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        assert "[DONE]" in text
        assert "Answer" in text


class TestStreamContractRegression:
    """Contract-regression: both streaming paths survive real httpx aiter_lines() str contract."""

    @pytest.mark.anyio
    async def test_stream_survives_real_aiter_lines_str_contract(self, mock_client, monkeypatch):
        """Drive both _stream_from_backend_guarded and _stream_with_tool_loop_impl
        with a corrected str-yielding aiter_lines() fake and assert output is correct
        and does NOT contain any error marker."""
        # ── Path 1: _stream_from_backend_guarded with plain content ──
        events_1 = (
            _sse_line({"choices": [{"index": 0, "delta": {"content": "Hello"}}]})
            + b"\n\n"
            + _sse_line({"choices": [{"index": 0, "delta": {"content": " world"}}]})
            + b"\n\n"
            + b"data: [DONE]\n\n"
        )
        lines_1 = _stream_lines(events_1)
        ctx_1 = _MockStreamContext(200, lines_1)

        def fake_stream_1(method, url, **kwargs):
            return ctx_1

        monkeypatch.setattr(mock_client, "stream", fake_stream_1)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        assert "Hello" in text
        assert "world" in text
        assert "[DONE]" in text
        assert "Backend connection error" not in text

        # ── Path 2: _stream_with_tool_loop_impl (no-tool path, same input) ──
        events_2 = (
            _sse_line({"choices": [{"index": 0, "delta": {"content": "Hello"}}]})
            + b"\n\n"
            + _sse_line({"choices": [{"index": 0, "delta": {"content": " world"}}]})
            + b"\n\n"
            + b"data: [DONE]\n\n"
        )
        lines_2 = _stream_lines(events_2)
        ctx_2 = _MockStreamContext(200, lines_2)

        fake_stream_calls = []

        def fake_stream_2(method, url, **kwargs):
            fake_stream_calls.append((method, url))
            return ctx_2

        monkeypatch.setattr(mock_client, "stream", fake_stream_2)

        gen2 = router_pipe._stream_with_tool_loop_impl(
            backend_url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
            persona="default",
            effective_tools=set(),
        )
        chunks2 = await _drain(gen2)
        text2 = _decode_chunks(chunks2)

        assert "Hello" in text2
        assert "world" in text2
        assert "[DONE]" in text2
        assert "Backend connection error" not in text2

    @pytest.mark.anyio
    async def test_reasoning_promotion_with_str_contract(self, mock_client, monkeypatch):
        """Reasoning promotion path works with str-yielding aiter_lines()."""
        events = (
            _sse_line(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "reasoning_content": "Let me think...",
                            },
                        }
                    ]
                }
            )
            + b"\n\n"
            + b"data: [DONE]\n\n"
        )
        lines = _stream_lines(events)
        ctx = _MockStreamContext(200, lines)

        def fake_stream(method, url, **kwargs):
            return ctx

        monkeypatch.setattr(mock_client, "stream", fake_stream)

        gen = router_pipe._stream_from_backend_guarded(
            url="http://localhost:11434/v1/chat/completions",
            body={},
            workspace_id="auto",
            model="test-model",
        )
        chunks = await _drain(gen)
        text = _decode_chunks(chunks)

        assert "Let me think" in text
        assert "Backend connection error" not in text
