"""Answer/reasoning channel separation across router boundaries."""

from __future__ import annotations

import json
from typing import Any

import pytest

import portal.platform.inference.router.streaming as streaming
from portal.platform.inference.router.thinking import (
    NO_ANSWER_MESSAGE,
    ThinkTagFilter,
    normalize_think_message,
)


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
