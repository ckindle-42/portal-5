"""P-4 detect (pipeline) and harness parity (400 prompt too long -> context_overflow)."""

from __future__ import annotations

from portal.platform.inference.router import truncation
from tests.wfe import runner


def _body(chars: int) -> dict:
    return {"messages": [{"role": "user", "content": "x" * chars}]}


def test_window_from_tag_suffix() -> None:
    assert truncation.window_of("gemma4:12b-it-qat-ctx8k") == 8192
    assert truncation.window_of("m:q4-CTX16K") == 16384
    assert truncation.window_of("gemma4:12b") is None


def test_flags_truncated_prompt_and_notice_once() -> None:
    truncation.set_estimate(_body(80_000))  # ~20k tokens estimated
    assert truncation.check("gemma4:12b-it-qat-ctx8k", "ws", 4099)
    notice = truncation.take_notice()
    assert "truncated" in notice and "8,192" in notice
    assert truncation.take_notice() == ""


def test_no_flag_when_prompt_fits_or_untagged() -> None:
    truncation.set_estimate(_body(8_000))
    assert not truncation.check("gemma4:12b-it-qat-ctx8k", "ws", 2000)
    truncation.set_estimate(_body(80_000))
    assert not truncation.check("gemma4:12b", "ws", 4099)
    # reported count above the window means the engine kept it all
    assert not truncation.check("gemma4:12b-it-qat-ctx8k", "ws", 20_000)


def test_harness_parity_400_prompt_too_long() -> None:
    err = RuntimeError(
        'HTTP 400 from http://x: {"detail":"request (20082 tokens) exceeds the available '
        'context size (8192 tokens), try increasing it"}'
    )
    assert runner._is_prompt_too_long(err)
    assert not runner._is_prompt_too_long(RuntimeError("HTTP 500 from x: boom"))
    assert not runner._is_prompt_too_long(RuntimeError("HTTP 400 from x: bad json"))
    tr = [{"turn": 1, "harness_error": "x", "context_overflow": "HTTP 400 prompt too long: y"}]
    assert "prompt too long" in (runner.context_overflow(tr, 8192) or "")
