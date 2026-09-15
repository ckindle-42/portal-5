"""The compliance reading transport: reasoning is a channel, not a leak.

The suppression this transport removes (946196bb) was introduced because a
thinking seat leaked ``<think>`` into strict-JSON content or ran out of predict
budget before the closing brace. That is a ``/v1``/inline-template phenomenon;
on native ``/api/chat`` the trace arrives as ``message.thinking``, separate from
``message.content``. These tests pin both halves of that claim, plus the
downgrade path — which is not hypothetical: two of the three D0-M council seats
answer HTTP 400 on ``think:true``.
"""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from portal.modules.compliance.core import reading_transport
from portal.modules.compliance.core.reading_transport import chat, strip_inline_reasoning


def _http_400(message: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        reading_transport._ENDPOINT,
        400,
        "Bad Request",
        {},  # type: ignore[arg-type]
        io.BytesIO(json.dumps({"error": message}).encode()),
    )


class _Server:
    """A fake Ollama that records every payload it was sent."""

    def __init__(self, *, thinking_capable: bool, content: str = "{}", thinking: str = "") -> None:
        self.thinking_capable = thinking_capable
        self.content = content
        self.thinking = thinking
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        self.payloads.append(json.loads(json.dumps(payload)))
        if payload.get("think") and not self.thinking_capable:
            raise _http_400(f'"{payload["model"]}" does not support thinking')
        message: dict[str, Any] = {"content": self.content}
        if payload.get("think"):
            message["thinking"] = self.thinking
        return {"message": message, "eval_count": 7}


@pytest.fixture(autouse=True)
def _clear_capability_cache():
    reading_transport._THINK_CAPABLE.clear()
    yield
    reading_transport._THINK_CAPABLE.clear()


def test_thinking_is_requested_and_preserved(monkeypatch):
    server = _Server(thinking_capable=True, content='{"ok": true}', thinking="step one, step two")
    monkeypatch.setattr(reading_transport, "_post", server)

    result = chat("qwen38", "sys", "user", budget=8192, think=True)

    assert server.payloads[0]["think"] is True
    assert server.payloads[0]["options"]["num_predict"] == 8192
    # the trace is kept as an audit artifact, and never mixed into the answer
    assert result.thinking == "step one, step two"
    assert result.content == '{"ok": true}'
    assert json.loads(result.content) == {"ok": True}
    assert result.reasoned is True
    assert result["downgraded"] == ""


def test_http_400_downgrades_once_and_is_recorded(monkeypatch):
    server = _Server(thinking_capable=False, content='{"relation": "SAME"}')
    monkeypatch.setattr(reading_transport, "_post", server)

    # think is asked for explicitly: DEFAULT_EFFORT is False by measurement, so
    # the downgrade path is only reachable when a caller opts in to reasoning
    result = chat("granite4.1:30b-ctx16k", "sys", "user", think=True)

    # one rejected attempt, one retry without the flag — not a silent failure
    assert len(server.payloads) == 2
    assert server.payloads[0]["think"] is True
    # explicitly false, never omitted: omitting the key leaves the model's own
    # template in charge, which for a thinking template means it reasons anyway
    assert server.payloads[1]["think"] is False
    assert result.content == '{"relation": "SAME"}'
    # the answer is usable, but it must never present itself as a reasoned one
    assert result.reasoned is False
    assert "does not support thinking" in result["downgraded"]
    assert "granite4.1:30b-ctx16k" in result["downgraded"]


def test_capability_is_cached_so_the_400_is_paid_once(monkeypatch):
    server = _Server(thinking_capable=False)
    monkeypatch.setattr(reading_transport, "_post", server)

    chat("mistral-small3.2:24b-instruct-2506-q4_K_M", "sys", "user", think=True)
    server.payloads.clear()
    second = chat("mistral-small3.2:24b-instruct-2506-q4_K_M", "sys", "user", think=True)

    # the second call never asks again, so a three-seat council pays the
    # rejection once per model per process, not once per Part
    assert len(server.payloads) == 1
    assert server.payloads[0]["think"] is False
    assert second.reasoned is False
    assert reading_transport._THINK_CAPABLE == {"mistral-small3.2:24b-instruct-2506-q4_K_M": False}


def test_a_non_400_error_is_not_swallowed(monkeypatch):
    def boom(payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        raise urllib.error.HTTPError(
            reading_transport._ENDPOINT,
            500,
            "Server Error",
            {},
            None,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(reading_transport, "_post", boom)
    # a downgrade is only ever a capability answer; a real fault must surface
    with pytest.raises(urllib.error.HTTPError):
        chat("qwen38", "sys", "user", think=True)


def test_inline_think_block_is_stripped_from_content(monkeypatch):
    server = _Server(
        thinking_capable=True,
        content='<think>the model reasoned inline</think>\n{"relation": "SAME"}',
    )
    monkeypatch.setattr(reading_transport, "_post", server)

    result = chat("some-non-native-template", "sys", "user")

    # exactly the 946196bb failure, now handled by parsing rather than by
    # disabling the model's reasoning
    assert result.content == '{"relation": "SAME"}'
    assert json.loads(result.content) == {"relation": "SAME"}


def test_think_false_is_honoured_when_a_caller_asks_for_it(monkeypatch):
    server = _Server(thinking_capable=True, thinking="unused")
    monkeypatch.setattr(reading_transport, "_post", server)

    result = chat("qwen38", "sys", "user", think=False)

    # the caller asked for suppression, so it must be sent as an explicit
    # false — this is the exact defect the case-10 small proof caught: an
    # omitted key measured identically to think:true on Qwen3.8
    assert server.payloads[0]["think"] is False
    assert result.reasoned is False
    assert result["downgraded"] == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<think>a</think>{}", "{}"),
        ("<think>a</think>\n\n  {}", "{}"),
        ("<THINK>a</THINK>{}", "{}"),
        ("<think>line\nline</think>{}", "{}"),
        ("{}", "{}"),
        ("", ""),
    ],
)
def test_strip_inline_reasoning_cases(raw, expected):
    assert strip_inline_reasoning(raw) == expected


def test_the_think_key_is_never_omitted(monkeypatch):
    """The invariant the case-10 small proof bought.

    An omitted ``think`` key is not suppression — it hands control to the
    model's own chat template, and a Qwen3/DeepSeek/GLM-Z1 template opens
    ``<think>`` by default. Measured live on Qwen3.8-27B with the real
    alignment packet: omitting the key and sending ``think: true`` produced
    byte-identical responses (34097 thinking chars, eval_count 7996 both
    times). A transport that omits the key cannot express suppression at all,
    so an arm that believes it measured ``think:false`` measures nothing.
    """
    for capable, asked in ((True, True), (True, False), (False, True)):
        reading_transport._THINK_CAPABLE.clear()
        server = _Server(thinking_capable=capable)
        monkeypatch.setattr(reading_transport, "_post", server)
        chat("m", "sys", "user", think=asked)
        for payload in server.payloads:
            assert "think" in payload, f"think omitted (capable={capable}, asked={asked})"
            assert isinstance(payload["think"], bool)


def test_default_effort_is_the_measured_one(monkeypatch):
    """The default is a measurement, not a preference.

    On the real case-10 alignment packet think false/low/medium/true all
    returned the identical correct reading, at 52s / 180s / 224s / 683s. `true`
    is the worst of them, because this roster's template reads
    `reasoning_effort|default('xhigh')`. So an unqualified call must not buy
    reasoning: raising the effort is a per-call-site decision backed by a
    measurement on that call site.
    """
    assert reading_transport.DEFAULT_EFFORT is False

    server = _Server(thinking_capable=True, thinking="should not be requested")
    monkeypatch.setattr(reading_transport, "_post", server)
    result = chat("qwen38", "sys", "user")

    assert server.payloads[0]["think"] is False
    assert result.reasoned is False
    # and a caller can still opt in, per call, without touching a global
    server.payloads.clear()
    assert chat("qwen38", "sys", "user", think="low").reasoned is True
    assert server.payloads[0]["think"] == "low"
