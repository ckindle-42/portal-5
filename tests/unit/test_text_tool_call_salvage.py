"""Text-written tool-call salvage (P5-OMLX-QWEN3CODER-TOOLTEXT-001).

Qwen3-Coder on oMLX sometimes skips the ``<tool_call>`` opener, so the call
arrives as plain content. The pipeline recovers it when tools were offered.
"""

from __future__ import annotations

import json
import typing
from unittest.mock import MagicMock

import pytest

import portal.platform.inference.router.streaming as streaming
from portal.platform.inference.router.tools import (
    TextToolCallHoldback,
    salvage_text_tool_calls,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}, "days": {"type": "integer"}},
            },
        },
    }
]
# Verbatim failure captured from oMLX at the card sampling, 2026-09-25.
OBSERVED = (
    "Paris\n<function=get_weather>\n<parameter=city>\nParis\n</parameter>\n"
    "</function>\n</tool_call>"
)


def test_salvages_observed_failure():
    text, calls = salvage_text_tool_calls(OBSERVED, TOOLS)
    assert text == "Paris"
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_weather"
    assert json.loads(calls[0]["function"]["arguments"]) == {"city": "Paris"}


def test_typed_parameters_and_multiple_calls():
    content = (
        "<tool_call>\n<function=get_weather>\n<parameter=city>\nOslo\n</parameter>\n"
        "<parameter=days>\n3\n</parameter>\n</function>\n</tool_call>\n"
        "<tool_call>\n<function=get_weather>\n<parameter=city>\n42\n</parameter>\n"
        "</function>\n</tool_call>"
    )
    text, calls = salvage_text_tool_calls(content, TOOLS)
    assert text == ""
    assert [json.loads(c["function"]["arguments"]) for c in calls] == [
        {"city": "Oslo", "days": 3},
        {"city": "42"},
    ]
    assert calls[0]["id"] != calls[1]["id"]


@pytest.mark.parametrize(
    "content,tools",
    [
        (OBSERVED, None),
        (OBSERVED.replace("get_weather", "rm_rf"), TOOLS),
        ("Plain answer with no call.", TOOLS),
        ("<function=get_weather> never closed", TOOLS),
    ],
)
def test_no_salvage_leaves_text_unchanged(content, tools):
    assert salvage_text_tool_calls(content, tools) == (content, [])


def test_holdback_splits_marker_across_chunks():
    hb = TextToolCallHoldback()
    assert hb.feed("Paris\n<fun") == "Paris\n"
    assert hb.feed("ction=get_weather>") == ""
    assert hb.holding
    assert hb.take() == "<function=get_weather>"


def test_holdback_releases_false_prefix():
    hb = TextToolCallHoldback()
    assert hb.feed("a <") == "a "
    assert hb.feed("b> c") == "<b> c"
    assert not hb.holding
    assert hb.take() == ""


# ── streaming tool loop ─────────────────────────────────────────────


def _frame(delta: dict, finish: str | None = None) -> str:
    return "data: " + json.dumps(
        {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    )


class _Ctx:
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def __aenter__(self):
        ctx = self

        class _Resp:
            status_code = 200

            async def aiter_lines(self):
                for line in ctx._lines:
                    yield line

        return _Resp()

    async def __aexit__(self, *_: typing.Any):
        pass


async def _run(monkeypatch, hops: list[list[str]]):
    client = MagicMock()
    client.stream = MagicMock(side_effect=[_Ctx(h) for h in hops])
    monkeypatch.setattr(streaming, "_http_client", client)
    dispatched: list[list[dict]] = []

    async def fake_dispatch(calls, *args):
        dispatched.append(calls)
        return {"role": "assistant", "content": None, "tool_calls": calls}, [
            {"role": "tool", "tool_call_id": c["id"], "content": "18 C, sunny"} for c in calls
        ]

    monkeypatch.setattr(streaming, "_dispatch_hop_tool_calls", fake_dispatch)
    out = b"".join(
        [
            c
            async for c in streaming._stream_with_tool_loop_impl(
                backend_url="http://omlx/v1/chat/completions",
                body={"model": "m", "messages": [], "tools": TOOLS},
                workspace_id="auto-coding",
                model="m",
                persona="",
                effective_tools={"get_weather"},
            )
        ]
    ).decode()
    return out, dispatched


@pytest.mark.anyio
async def test_stream_dispatches_text_call_and_hides_xml(monkeypatch):
    hop1 = [
        _frame({"content": "Paris\n<func"}),
        _frame({"content": "tion=get_weather>\n<parameter=city>\nParis\n</parameter>\n"}),
        _frame({"content": "</function>\n</tool_call>"}),
        _frame({}, "stop"),
        "data: [DONE]",
    ]
    hop2 = [_frame({"content": "It is 18 C and sunny."}), _frame({}, "stop"), "data: [DONE]"]
    out, dispatched = await _run(monkeypatch, [hop1, hop2])
    assert len(dispatched) == 1
    assert json.loads(dispatched[0][0]["function"]["arguments"]) == {"city": "Paris"}
    assert "<function" not in out and "</tool_call>" not in out
    assert "sunny" in out
    assert out.count("[DONE]") == 1


@pytest.mark.anyio
async def test_stream_releases_unparseable_text_in_order(monkeypatch):
    hop1 = [
        _frame({"content": "Use <function=rm_rf>x</function> like this."}),
        _frame({}, "stop"),
        "data: [DONE]",
    ]
    out, dispatched = await _run(monkeypatch, [hop1])
    assert dispatched == []
    assert "<function=rm_rf>x</function> like this." in out
    assert out.index("rm_rf") < out.index('"finish_reason": "stop"') < out.index("[DONE]")
    assert out.count("[DONE]") == 1
