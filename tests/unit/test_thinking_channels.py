"""Answer/reasoning channel separation across router boundaries."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import portal.platform.inference.router.streaming as streaming
from portal.platform.inference.router.thinking import (
    NO_ANSWER_MESSAGE,
    ThinkTagFilter,
    normalize_think_message,
)

DONE = b"data: [DONE]\n\n"


def _decode_payloads(chunks: list[bytes]) -> list[dict[str, Any]]:
    out = []
    for chunk in chunks:
        for line in chunk.decode().splitlines():
            if line.startswith("data: ") and line[6:] != "[DONE]":
                try:
                    out.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    continue
    return out


def _content(payloads: list[dict[str, Any]]) -> str:
    return "".join(
        (choice.get("delta") or {}).get("content") or ""
        for payload in payloads
        for choice in payload.get("choices") or []
    )


def _reasoning(payloads: list[dict[str, Any]], name: str) -> str:
    return "".join(
        (choice.get("delta") or {}).get(name) or ""
        for payload in payloads
        for choice in payload.get("choices") or []
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            'A<think>private thought</think>B "<think>quoted markup</think>" '
            "`<think>inline code</think>`\n```html\n<think>fenced code</think>\n```\n  tail  ",
            'AB "<think>quoted markup</think>" `<think>inline code</think>`\n'
            "```html\n<think>fenced code</think>\n```\n  tail  ",
        ),
        ("before<THINK>first</THINK>middle<think>second</think>after", "beforemiddleafter"),
        ("  <think>hidden</think>  keep\n\n  trailing  ", "    keep\n\n  trailing  "),
    ],
)
def test_inline_think_filter_is_chunk_boundary_safe_and_byte_preserving(source, expected):
    for split in range(len(source) + 1):
        filt = ThinkTagFilter()
        visible = filt.feed(source[:split]) + filt.feed(source[split:], final=True)
        assert visible == expected, f"split={split}"


def test_unterminated_protocol_block_is_discarded_at_terminal_boundary():
    filt = ThinkTagFilter()
    assert filt.feed("Visible answer <think>secret split") == "Visible answer "
    assert filt.feed(" reasoning", final=True) == ""
    assert filt.removed


def test_incomplete_tag_prefix_and_legitimate_answer_whitespace_are_preserved():
    filt = ThinkTagFilter()
    assert filt.feed("  \n  `") == "  \n  "
    assert filt.feed("code\n") == "`code\n"
    assert filt.feed("tail  <thi", final=True) == "tail  <thi"


@pytest.mark.parametrize("field", ["reasoning", "reasoning_content", "thinking"])
def test_non_streaming_normalization_never_promotes_reasoning(field):
    msg = {"content": "", field: "REASONING_SENTINEL"}
    assert normalize_think_message(msg)
    assert msg["content"] == ""
    assert msg[field] == "REASONING_SENTINEL"


def test_non_streaming_normalization_filters_inline_blocks_but_preserves_literal_markup():
    msg = {
        "content": 'prefix<think>hidden</think>suffix "<think>literal</think>"',
    }
    assert not normalize_think_message(msg)
    assert msg["content"] == 'prefixsuffix "<think>literal</think>"'


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"enable_thinking": False}, False),
        ({"enable_thinking": True}, True),
        ({"chat_template_kwargs": {"enable_thinking": False}}, False),
        ({"chat_template_kwargs": {"enable_thinking": True}}, True),
        ({"reasoning_effort": "none"}, False),
        ({"reasoning_effort": "high"}, True),
        ({"options": {"think": False}}, False),
        ({}, True),
    ],
)
def test_effective_thinking_flag_reads_engine_specific_request_fields(body, expected):
    assert streaming._thinking_enabled(body) is expected


class _Response:
    status_code = 200

    def __init__(self, lines: list[str]):
        self.lines = lines

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self.lines:
            yield line


class _Context:
    def __init__(self, response: _Response):
        self.response = response

    async def __aenter__(self) -> _Response:
        return self.response

    async def __aexit__(self, *_: Any) -> None:
        return None


def _frame(delta: dict[str, Any], finish_reason: str | None = None) -> str:
    return "data: " + json.dumps(
        {"choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}
    )


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["reasoning", "reasoning_content", "thinking"])
@pytest.mark.parametrize("thinking_enabled", [False, True])
async def test_guarded_stream_keeps_reasoning_separate_and_classifies_empty_terminal(
    monkeypatch, field, thinking_enabled
):
    client = MagicMock()
    client.stream = lambda *_a, **_k: _Context(
        _Response(
            [
                _frame({field: "REASONING_SENTINEL"}),
                _frame({}, "length"),
                "data: [DONE]",
                _frame({"content": "AFTER_DONE_SENTINEL"}),
            ]
        )
    )
    monkeypatch.setattr(streaming, "_http_client", client)
    body = {"chat_template_kwargs": {"enable_thinking": thinking_enabled}}
    chunks = [
        chunk
        async for chunk in streaming._stream_from_backend_guarded(
            "http://engine/v1/chat/completions", body, workspace_id="ws", model="m"
        )
    ]
    payloads = _decode_payloads(chunks)
    rendered = _content(payloads)
    serialized = b"".join(chunks).decode()
    assert rendered == NO_ANSWER_MESSAGE
    assert "AFTER_DONE_SENTINEL" not in serialized
    assert payloads[-1]["choices"][0]["finish_reason"] == "length"
    assert chunks[-1] == DONE
    if thinking_enabled:
        assert _reasoning(payloads, field) == "REASONING_SENTINEL"
    else:
        assert _reasoning(payloads, field) == ""
        assert "REASONING_SENTINEL" not in serialized


def test_json_to_sse_fallback_does_not_promote_thoughts():
    payloads = [
        json.loads(frame.decode().split("data: ", 1)[1])
        for frame in streaming._json_completion_to_sse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "SECRET",
                        },
                        "finish_reason": "length",
                    }
                ]
            },
            "ws",
        )
        if b"[DONE]" not in frame
    ]
    assert _content(payloads) == NO_ANSWER_MESSAGE
    assert _reasoning(payloads, "reasoning_content") == "SECRET"
    assert payloads[-1]["choices"][0]["finish_reason"] == "length"


def test_non_streaming_reasoning_only_is_an_explicit_incomplete_answer(monkeypatch):
    import portal.platform.inference.router.non_streaming as non_streaming

    monkeypatch.setattr(non_streaming, "_record_usage", lambda **_kwargs: None)
    response = non_streaming._apply_non_stream_response(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "", "thinking": "PRIVATE"},
                    "finish_reason": "length",
                }
            ]
        },
        SimpleNamespace(id="test-engine"),
        "test-workspace",
        "test-model",
        0.0,
    )
    body = json.loads(response.body)
    message = body["choices"][0]["message"]
    assert message["content"] == NO_ANSWER_MESSAGE
    assert message["thinking"] == "PRIVATE"
    assert body["choices"][0]["finish_reason"] == "length"


# ── Inline ``<think>`` text is reasoning, never "no answer" ────────────────────


@pytest.mark.parametrize(
    ("source", "visible", "reasoning"),
    [
        (
            "<think>extract the names first</think>Alice met Bob in Paris.",
            "Alice met Bob in Paris.",
            "extract the names first",
        ),
        ("<think>extract the names first", "", "extract the names first"),
        ("<thi" + "nk>extract the names first", "", "extract the names first"),
        ("Alice met Bob in Paris.", "Alice met Bob in Paris.", ""),
    ],
    ids=["opened-then-closed", "opened-never-closed", "tag-split", "plain-content"],
)
def test_inline_think_is_reasoning_at_every_chunk_split(source, visible, reasoning):
    for split in range(len(source) + 1):
        filt = ThinkTagFilter()
        shown = filt.feed(source[:split])
        thoughts = filt.take_reasoning()
        shown += filt.feed(source[split:], final=True)
        thoughts += filt.take_reasoning()
        assert shown == visible, f"split={split}"
        assert thoughts == reasoning, f"split={split}"


def test_quoted_literal_think_markup_stays_content_and_is_not_reasoning():
    filt = ThinkTagFilter()
    assert filt.feed('prefix "<think>literal</think>"', final=True) == (
        'prefix "<think>literal</think>"'
    )
    assert filt.take_reasoning() == ""


def test_non_streaming_inline_think_becomes_reasoning_content():
    msg = {"content": "<think>private plan</think>"}
    assert normalize_think_message(msg)
    assert msg["content"] == ""
    assert msg["reasoning_content"] == "private plan"


def test_non_streaming_inline_think_is_hidden_when_thinking_is_off():
    msg = {"content": "<think>private plan</think>"}
    assert normalize_think_message(msg, thinking_allowed=False)
    assert msg["content"] == ""
    assert "reasoning_content" not in msg


def test_non_streaming_inline_think_does_not_swallow_the_answer():
    msg = {"content": "<think>private plan</think>Alice met Bob in Paris."}
    assert not normalize_think_message(msg)
    assert msg["content"] == "Alice met Bob in Paris."
    assert msg["reasoning_content"] == "private plan"


def test_json_to_sse_fallback_carries_inline_think_as_reasoning():
    payloads = [
        json.loads(frame.decode().split("data: ", 1)[1])
        for frame in streaming._json_completion_to_sse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "<think>private plan",
                        },
                        "finish_reason": "length",
                    }
                ]
            },
            "ws",
        )
        if b"[DONE]" not in frame
    ]
    assert _content(payloads) == NO_ANSWER_MESSAGE
    assert _reasoning(payloads, "reasoning_content") == "private plan"
    assert payloads[-1]["choices"][0]["finish_reason"] == "length"


@pytest.mark.anyio
@pytest.mark.parametrize("thinking_enabled", [True, False])
async def test_streamed_inline_think_never_closed_is_reasoning_only(monkeypatch, thinking_enabled):
    client = MagicMock()
    client.stream = lambda *_a, **_k: _Context(
        _Response(
            [
                _frame({"content": "<think>The user asks: extract the names. No"}),
                _frame({}, "length"),
                "data: [DONE]",
            ]
        )
    )
    monkeypatch.setattr(streaming, "_http_client", client)
    body = {"chat_template_kwargs": {"enable_thinking": thinking_enabled}}
    chunks = [
        chunk
        async for chunk in streaming._stream_from_backend_guarded(
            "http://engine/v1/chat/completions", body, workspace_id="ws", model="m"
        )
    ]
    payloads = _decode_payloads(chunks)
    serialized = b"".join(chunks).decode()
    assert _content(payloads) == NO_ANSWER_MESSAGE
    assert "<think>" not in serialized
    assert payloads[-1]["choices"][0]["finish_reason"] == "length"
    if thinking_enabled:
        assert _reasoning(payloads, "reasoning_content") == ("The user asks: extract the names. No")
    else:
        assert _reasoning(payloads, "reasoning_content") == ""
        assert "The user asks" not in serialized


@pytest.mark.anyio
async def test_streamed_inline_think_split_across_chunks_releases_the_answer(monkeypatch):
    client = MagicMock()
    client.stream = lambda *_a, **_k: _Context(
        _Response(
            [
                _frame({"content": "<thi"}),
                _frame({"content": "nk>private plan</thi"}),
                _frame({"content": "nk>Alice met Bob in Paris."}),
                _frame({}, "stop"),
                "data: [DONE]",
            ]
        )
    )
    monkeypatch.setattr(streaming, "_http_client", client)
    chunks = [
        chunk
        async for chunk in streaming._stream_from_backend_guarded(
            "http://engine/v1/chat/completions", {}, workspace_id="ws", model="m"
        )
    ]
    payloads = _decode_payloads(chunks)
    assert _content(payloads) == "Alice met Bob in Paris."
    assert _reasoning(payloads, "reasoning_content") == "private plan"
    assert "<think>" not in b"".join(chunks).decode()
    assert payloads[-1]["choices"][0]["finish_reason"] == "stop"


@pytest.mark.anyio
async def test_inline_think_turn_grades_reasoning_only_in_the_trace(monkeypatch):
    """The stream this pipeline now sends for LFM2.5's unclosed block grades WARN, not FAIL."""
    from portal.platform.inference.cli.trace import workspaces

    client = MagicMock()
    client.stream = lambda *_a, **_k: _Context(
        _Response(
            [
                _frame(
                    {
                        "content": (
                            "<think>The user asks: extract the names from: Alice met "
                            "Bob in Paris. So respond with names. No"
                        )
                    }
                ),
                _frame({}, "length"),
                "data: "
                + json.dumps(
                    {
                        "choices": [],
                        "usage": {"completion_tokens": 24, "source": "pipeline"},
                    }
                ),
                "data: [DONE]",
            ]
        )
    )
    monkeypatch.setattr(streaming, "_http_client", client)
    chunks = [
        chunk
        async for chunk in streaming._stream_from_backend_guarded(
            "http://engine/v1/chat/completions",
            {"stream_options": {"include_usage": True}},
            workspace_id="auto-documents::extract-uncensored",
            model="m",
        )
    ]
    events = [
        (index * 0.1, frame)
        for index, chunk in enumerate(chunks)
        for line in chunk.decode().splitlines()
        if (frame := workspaces.parse_sse(line)) is not None
    ]
    stats = workspaces.summarize_turn(events)
    assert stats.text == NO_ANSWER_MESSAGE
    assert stats.reasoning_deltas >= 1
    seat = workspaces.Seat("auto-documents::extract-uncensored", "m")
    route = ["auto-documents::extract-uncensored", "ollama-general", "m"]
    hop = workspaces.seat_hop(seat, workspaces.StreamedTurn(200, route, stats))
    assert hop.status is workspaces.Status.WARN
    assert "reasoning-only" in hop.observed


@pytest.mark.anyio
async def test_tool_loop_inline_think_never_closed_is_reasoning_only(monkeypatch):
    client = MagicMock()
    client.stream = lambda *_a, **_k: _Context(
        _Response(
            [
                _frame({"content": "<think>checking the workspace"}),
                _frame({}, "length"),
                "data: [DONE]",
            ]
        )
    )
    monkeypatch.setattr(streaming, "_http_client", client)
    body = {"messages": [{"role": "user", "content": "Extract the names."}]}
    chunks = [
        chunk
        async for chunk in streaming._stream_with_tool_loop_impl(
            "http://engine/v1/chat/completions", body, "ws", "m", "", set()
        )
    ]
    payloads = _decode_payloads(chunks)
    assert _content(payloads) == NO_ANSWER_MESSAGE
    assert _reasoning(payloads, "reasoning_content") == "checking the workspace"
    assert chunks[-1] == DONE
    assert payloads[-1]["choices"][0]["finish_reason"] == "length"
