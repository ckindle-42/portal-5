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
from portal.modules.compliance.core.transport_dialects import OllamaNative


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

    def __call__(self, payload: dict[str, Any], timeout: int, dialect=None) -> dict[str, Any]:
        self.payloads.append(json.loads(json.dumps(payload)))
        if payload.get("think") and not self.thinking_capable:
            raise _http_400(f'"{payload["model"]}" does not support thinking')
        message: dict[str, Any] = {"content": self.content}
        if payload.get("think"):
            message["thinking"] = self.thinking
        return {"message": message, "eval_count": 7}


@pytest.fixture(autouse=True)
def _pin_native_transport(monkeypatch):
    """These tests pin the NATIVE wire contract. The P5-FANOUT-001 default
    (``COMPLIANCE_TRANSPORT=pipeline``) would resolve them at the pipeline
    dialect, which owns its transport and bypasses the ``_post`` fakes below;
    ``ollama-native`` restores the resolution these tests were written under."""
    monkeypatch.setenv("COMPLIANCE_TRANSPORT", "ollama-native")


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
    # `budget` is the ANSWER budget; the reasoning allowance is added on top, so
    # turning reasoning on cannot shrink the answer.
    assert server.payloads[0]["options"]["num_predict"] == (
        8192 + reading_transport.DEFAULT_REASONING_ALLOWANCE
    )
    assert result["answer_budget"] == 8192
    assert result["reasoning_allowance"] == reading_transport.DEFAULT_REASONING_ALLOWANCE
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
    def boom(payload: dict[str, Any], timeout: int, dialect=None) -> dict[str, Any]:
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


# ── the answer budget, the reasoning allowance, and the ceiling ──────────────
#
# TASK_COMPLIANCE_PROVE_CIP_007_V1 P0.2/P1.3. Three things the transport used to
# leave implicit and one it used to get wrong:
#
# * one `num_predict` covered thinking AND content, so the trace could starve
#   the answer to nothing and the empty string travelled as a terse answer;
# * temperature was an unnamed literal, so a declared lane policy and the value
#   actually sent could never be compared;
# * an oversized prompt arrived as a bare `HTTPError` that killed the reading,
#   and was described in the module as a silent front-truncation — which this
#   runner does not do.


class _EmptyUnderReasoning:
    """A seat that spends its whole allowance thinking until the allowance
    doubles."""

    def __init__(self, *, succeed_at: int) -> None:
        self.succeed_at = succeed_at
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any], timeout: int, dialect=None) -> dict[str, Any]:
        self.payloads.append(json.loads(json.dumps(payload)))
        predict = payload["options"]["num_predict"]
        content = "the answer" if predict >= self.succeed_at else ""
        return {"message": {"content": content, "thinking": "x" * 500}, "eval_count": 9}


def _no_ceiling(monkeypatch):
    # Post-seam the ceiling and applied window come from the resolved dialect,
    # so that is the interception point (P1.2: chat delegates to _dialect).
    monkeypatch.setattr(OllamaNative, "seat_ceiling", lambda self, model: 0)
    monkeypatch.setattr(OllamaNative, "applied_context_length", lambda self, model: 0)


def test_budget_is_an_alias_for_answer_budget_and_reasoning_is_free_of_it(monkeypatch):
    _no_ceiling(monkeypatch)
    server = _Server(thinking_capable=True, content="prose", thinking="trace")
    monkeypatch.setattr(reading_transport, "_post", server)

    off = chat("qwen38", "sys", "user", budget=1000, think=False)
    assert server.payloads[-1]["options"]["num_predict"] == 1000
    assert off["reasoning_allowance"] == 0

    chat("qwen38", "sys", "user", answer_budget=1000, reasoning_allowance=250, think=True)
    assert server.payloads[-1]["options"]["num_predict"] == 1250


def test_temperature_is_the_named_default_and_is_recorded(monkeypatch):
    _no_ceiling(monkeypatch)
    server = _Server(thinking_capable=True, content="prose")
    monkeypatch.setattr(reading_transport, "_post", server)

    result = chat("qwen38", "sys", "user")

    assert reading_transport.DEFAULT_TEMPERATURE == 0.0
    assert server.payloads[0]["options"]["temperature"] == 0.0
    # recorded on the result, so an acceptance row carries the APPLIED value
    assert result["temperature"] == 0.0


def test_an_empty_answer_under_reasoning_retries_once_at_double_the_allowance(monkeypatch):
    _no_ceiling(monkeypatch)
    server = _EmptyUnderReasoning(succeed_at=1000 + 500)
    monkeypatch.setattr(reading_transport, "_post", server)

    result = chat("qwen38", "sys", "user", answer_budget=1000, reasoning_allowance=250, think=True)

    assert [p["options"]["num_predict"] for p in server.payloads] == [1250, 1500]
    assert result.content == "the answer"
    assert result["stop_reason"] == ""
    # both attempts are recorded, with the allowance each one had
    assert [a["reasoning_allowance"] for a in result["attempts"]] == [250, 500]


def test_a_still_empty_answer_is_a_budget_error_never_a_substantive_one(monkeypatch):
    _no_ceiling(monkeypatch)
    server = _EmptyUnderReasoning(succeed_at=10_000)
    monkeypatch.setattr(reading_transport, "_post", server)

    result = chat("qwen38", "sys", "user", answer_budget=1000, reasoning_allowance=250, think=True)

    assert result.content == ""
    assert result["stop_reason"] == "budget_exhausted_in_reasoning"
    assert len(result["attempts"]) == 2
    assert result["attempts"][-1]["thinking_chars"] == 500


def test_a_window_above_the_seat_ceiling_is_stated_not_clamped(monkeypatch):
    monkeypatch.setattr(OllamaNative, "seat_ceiling", lambda self, model: 32768)
    called: list[dict[str, Any]] = []
    monkeypatch.setattr(
        reading_transport, "_post", lambda p, t, dialect=None: called.append(p) or {}
    )

    with pytest.raises(reading_transport.ContextCeilingError) as excinfo:
        chat("qwen38", "sys", "user", num_ctx=65536)

    assert "65536" in str(excinfo.value) and "32768" in str(excinfo.value)
    assert called == []  # refused before the call, never silently reduced


def test_an_oversized_prompt_is_named_rather_than_killing_the_reading(monkeypatch):
    monkeypatch.setattr(OllamaNative, "seat_ceiling", lambda self, model: 262144)

    def overflow(payload, timeout, dialect=None):
        raise urllib.error.HTTPError(
            reading_transport._ENDPOINT,
            400,
            "Bad Request",
            {},  # type: ignore[arg-type]
            io.BytesIO(
                json.dumps(
                    {
                        "error": json.dumps(
                            {
                                "error": {
                                    "code": 400,
                                    "message": "request (33142 tokens) exceeds the available "
                                    "context size (32768 tokens), try increasing it",
                                    "type": "exceed_context_size_error",
                                    "n_prompt_tokens": 33142,
                                    "n_ctx": 32768,
                                }
                            }
                        )
                    }
                ).encode()
            ),
        )

    monkeypatch.setattr(reading_transport, "_post", overflow)

    with pytest.raises(reading_transport.ContextCeilingError) as excinfo:
        chat("qwen38", "sys", "user", num_ctx=32768, think=True)

    # the runner's own two numbers survive into the message
    assert "33142" in str(excinfo.value) and "32768" in str(excinfo.value)
    # and it is NOT mistaken for "does not support thinking": the think cache is
    # untouched, so the next call is not silently downgraded
    assert reading_transport._THINK_CAPABLE == {}
