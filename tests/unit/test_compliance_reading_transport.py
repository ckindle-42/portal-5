"""The compliance reading transport: reasoning is a channel, not a leak.

The suppression this transport removes (f350324a) was introduced because a
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

    def __call__(self, payload: dict[str, Any], timeout: int, dialect=None) -> dict[str, Any]:
        self.payloads.append(json.loads(json.dumps(payload)))
        if payload.get("think") and not self.thinking_capable:
            raise _http_400(f'"{payload["model"]}" does not support thinking')
        message: dict[str, Any] = {"content": self.content}
        if payload.get("think"):
            message["thinking"] = self.thinking
        return {"message": message, "eval_count": 7}


class _PipelineDialect:
    name = "pipeline"
    endpoint = "http://pipeline/v1/chat/completions"

    def __init__(
        self,
        content: str,
        reasoning: str,
        finish_reason: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.content = content
        self.reasoning = reasoning
        self.finish_reason = finish_reason
        self.tool_calls = tool_calls or []
        self.payloads: list[dict[str, Any]] = []

    def seat_ceiling(self, model: str) -> int:
        return 0

    def build(self, **kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    def post(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        self.payloads.append(payload)
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": self.content,
                        "reasoning_content": self.reasoning,
                        "tool_calls": self.tool_calls,
                    },
                    "finish_reason": self.finish_reason,
                }
            ],
            "usage": {"completion_tokens": 8192},
            "_portal": {
                "options_applied": {
                    "enable_thinking": True,
                    "output_limit": 8192,
                }
            },
        }

    def metrics(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"eval_count": 8192}

    def unpack(self, body: dict[str, Any]) -> tuple[str, str]:
        message = body["choices"][0]["message"]
        return message["content"], message["reasoning_content"]

    def applied_context_length(self, model: str) -> int:
        return 65536

    def context_source(self) -> str:
        return "workspace_policy"

    def classify_400(self, exc: urllib.error.HTTPError) -> str:
        return ""


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


def test_pipeline_applied_reasoning_and_finish_reason_are_observed():
    dialect = _PipelineDialect("", "private trace", "length")
    result = chat(
        "compliance-council-deepseek-r1",
        "system",
        "packet",
        budget=8192,
        think=False,
        dialect=dialect,
    )

    assert len(dialect.payloads) == 1  # workspace policy owns the fixed pipeline limit
    assert result.reasoned is True  # actual applied option overrides the caller default
    assert result.thinking == "private trace"
    assert result.content == ""  # a length terminal is never a vote
    assert result["finish_reason"] == "length"
    assert result["stop_reason"] == "budget_exhausted"
    assert result["eval_count"] == 8192
    assert result["usage"]["completion_tokens"] == 8192


def test_pipeline_reasoning_only_is_classified_but_tool_call_hop_survives():
    reasoning_only = _PipelineDialect("", "private trace", "stop")
    result = chat("council", "system", "packet", dialect=reasoning_only, think=False)
    assert result["stop_reason"] == "reasoning_only_no_answer"
    assert result.content == ""

    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "read", "arguments": "{}"},
    }
    tool_hop = _PipelineDialect("", "private trace", "tool_calls", [tool_call])
    result = chat("council", "system", "packet", dialect=tool_hop, think=False)
    assert result["stop_reason"] == ""
    assert result.tool_calls == [tool_call]


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
