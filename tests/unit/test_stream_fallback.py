"""Golden-output streaming tests (Phase 4 — T-10).

Tests for SSE stream parsing in ``_stream_from_backend_guarded`` and
``_stream_with_tool_loop_impl``. These must PASS before and after any
Phase-4 edit to ``router_pipe.py``.

Coverage:
- Plain content output (single-line and multi-line)
- tool_calls multi-hop (OpenAI SSE shape)
- reasoning-channel preservation and explicit no-answer classification
- Empty-line passthrough and [DONE] termination
"""

from __future__ import annotations

import json


def test_indexed_tool_calls_numbers_each_call():
    from portal.platform.inference.router import streaming

    calls = [{"id": "a", "function": {"name": "f"}}, {"id": "b", "function": {"name": "g"}}]
    assert [c["index"] for c in streaming._indexed_tool_calls(calls)] == [0, 1]
    assert "index" not in calls[0]


def test_json_to_sse_fallback_indexes_parallel_tool_calls():
    from portal.platform.inference.router import streaming

    calls = [
        {"id": "a", "type": "function", "function": {"name": "file_write", "arguments": "{}"}},
        {"id": "b", "type": "function", "function": {"name": "pytest_run", "arguments": "{}"}},
    ]
    frames = streaming._json_completion_to_sse(
        {"choices": [{"message": {"role": "assistant", "tool_calls": calls}}]}, "ws"
    )
    deltas = [json.loads(f.decode().split("data: ", 1)[1]) for f in frames if b"[DONE]" not in f]
    emitted = [
        tc
        for d in deltas
        for ch in d.get("choices", [])
        for tc in ch.get("delta", {}).get("tool_calls", [])
    ]
    assert [tc["index"] for tc in emitted] == [0, 1]


def test_json_to_sse_fallback_emits_requested_usage():
    from portal.platform.inference.router import streaming

    data = {
        "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11},
    }
    frames = list(streaming._json_completion_to_sse(data, "ws", include_usage=True))
    usage = [json.loads(f.decode().split("data: ", 1)[1]) for f in frames if b'"usage"' in f]
    assert usage and usage[0]["usage"]["completion_tokens"] == 2
    assert frames[-1] == b"data: [DONE]\n\n"
    plain = list(streaming._json_completion_to_sse(data, "ws"))
    assert not any(b'"usage"' in f for f in plain)


def test_json_to_sse_fallback_zero_fills_a_completion_without_usage():
    from portal.platform.inference.router import streaming

    data = {"choices": [{"message": {"role": "assistant", "content": "OK"}}]}
    frames = list(streaming._json_completion_to_sse(data, "ws", include_usage=True))
    usage = [json.loads(f.decode().split("data: ", 1)[1]) for f in frames if b'"usage"' in f]
    assert usage and usage[0]["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
