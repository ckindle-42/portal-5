"""Tool results stay within the context-derived byte budget across loop hops."""

from __future__ import annotations

import logging

import pytest

from portal.platform.inference.router.tool_repeat import (
    apply_tool_byte_budget,
    tool_result_byte_budget,
)

_DOCUMENT = "Invoice line\n" * 2000  # 26_000 bytes, above the rejected 4_000-char cap

_WALK = "A" * 600


def test_budget_is_half_the_window_at_two_bytes_per_token() -> None:
    assert tool_result_byte_budget(0) == 0
    assert tool_result_byte_budget(-1) == 0
    # 50% × 2 bytes/token = one byte of tool content per declared token.
    assert tool_result_byte_budget(8192) == 8192
    assert tool_result_byte_budget(98304) == 98304
    assert tool_result_byte_budget(98304) > len(_DOCUMENT.encode("utf-8"))


def test_budget_truncates_new_tool_results_to_remaining_bytes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    exact_message = {"role": "tool", "content": "x" * 100}
    exact = apply_tool_byte_budget(0, [exact_message], 100, "ws")
    assert exact == 100 and exact_message["content"] == "x" * 100
    ignored = apply_tool_byte_budget(0, [{"role": "assistant", "content": "x" * 500}], 10, "ws")
    assert ignored == 0
    multibyte_message = {"role": "tool", "content": "é" * 100}
    multibyte = apply_tool_byte_budget(0, [multibyte_message], 80, "ws")
    assert multibyte == 80
    assert len(multibyte_message["content"].encode("utf-8")) == 80
    assert "truncated" in multibyte_message["content"]
    small_message = {"role": "tool", "content": "prefix" * 20}
    small = apply_tool_byte_budget(0, [small_message], 40, "ws")
    assert small == 40
    assert small_message["content"].startswith("prefix")
    assert small_message["content"].endswith("[cut:budget]")
    caplog.clear()
    first = apply_tool_byte_budget(0, [{"role": "tool", "content": _WALK}], 1000, "ws")
    assert first == 600
    second_message = {"role": "tool", "content": "B" * 600}
    second = apply_tool_byte_budget(first, [second_message], 1000, "ws")
    assert second == 1000
    assert len(second_message["content"].encode("utf-8")) == 400
    hits = [r for r in caplog.records if "result truncated" in r.message]
    assert len(hits) == 1
    assert "accumulated=1200" in hits[0].message and "budget=1000" in hits[0].message
