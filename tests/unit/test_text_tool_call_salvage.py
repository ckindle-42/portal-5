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
from portal.platform.inference.router.preinject import (
    _apply_client_tools_only,
    _inject_system_prompt_append,
)
from portal.platform.inference.router.text_tool_calls import (
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


def test_salvages_json_tool_call_wrapper() -> None:
    content = (
        '<tool_call>\n{"name":"get_weather","arguments":{"city":"Oslo","days":3}}\n</tool_call>'
    )
    text, calls = salvage_text_tool_calls(content, TOOLS)
    assert text == ""
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_weather"
    assert json.loads(calls[0]["function"]["arguments"]) == {"city": "Oslo", "days": 3}


def test_salvages_json_wrapper_with_one_extra_closing_brace() -> None:
    content = '<tool_call>{"name":"get_weather","arguments":{"city":"Oslo"}}}</tool_call>'
    text, calls = salvage_text_tool_calls(content, TOOLS)
    assert text == ""
    assert len(calls) == 1
    assert json.loads(calls[0]["function"]["arguments"]) == {"city": "Oslo"}


@pytest.mark.parametrize(
    "content,tools",
    [
        (OBSERVED, None),
        (OBSERVED.replace("get_weather", "rm_rf"), TOOLS),
        ('<tool_call>{"name":"rm_rf","arguments":{}}</tool_call>', TOOLS),
        ("<|tool_call>call:rm_rf{q:1}<tool_call|>", TOOLS),
        ("<tool_call>{not json}</tool_call>", TOOLS),
        ('<tool_call>{"name":"get_weather","arguments":{}}}}</tool_call>', TOOLS),
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
async def test_stream_dispatches_json_tool_call_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    hop1 = [
        _frame(
            {
                "content": (
                    '<tool_call>\n{"name":"get_weather","arguments":{"city":"Oslo"}}}\n</tool_call>'
                )
            }
        ),
        _frame({}, "stop"),
        "data: [DONE]",
    ]
    hop2 = [_frame({"content": "It is 18 C and sunny."}), _frame({}, "stop"), "data: [DONE]"]
    out, dispatched = await _run(monkeypatch, [hop1, hop2])
    assert len(dispatched) == 1
    assert dispatched[0][0]["function"]["name"] == "get_weather"
    assert json.loads(dispatched[0][0]["function"]["arguments"]) == {"city": "Oslo"}
    assert "<tool_call>" not in out
    assert "sunny" in out


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


@pytest.mark.anyio
async def test_reasoning_only_remains_separate_and_is_not_an_answer(monkeypatch):
    hop1 = [
        _frame({"reasoning_content": "summarize"}),
        _frame({"reasoning_content": "(rows)"}),
        _frame({"reasoning_content": " 3."}),
        _frame({}, "stop"),
        "data: [DONE]",
    ]
    out, _ = await _run(monkeypatch, [hop1])
    payloads = [
        json.loads(line[6:])
        for line in out.splitlines()
        if line.startswith("data: ") and line[6:] != "[DONE]"
    ]
    content = "".join(
        (choice.get("delta") or {}).get("content") or ""
        for payload in payloads
        for choice in payload.get("choices") or []
    )
    reasoning = "".join(
        (choice.get("delta") or {}).get("reasoning_content") or ""
        for payload in payloads
        for choice in payload.get("choices") or []
    )
    assert content == streaming.NO_ANSWER_MESSAGE
    assert reasoning == "summarize(rows) 3."
    assert "summarize(rows) 3." not in content
    assert payloads[-1]["choices"][0]["finish_reason"] == "length"
    assert out.rstrip().endswith("data: [DONE]")


@pytest.mark.anyio
async def test_marked_workspace_uses_only_client_tools_and_skips_its_prompt(monkeypatch):
    workspace_id = "test-client-tools-only"
    monkeypatch.setitem(
        streaming.WORKSPACES,
        workspace_id,
        {
            "client_tools_only": True,
            "system_prompt_append": "\nserver tools prompt",
            "tools": ["execute_python"],
        },
    )
    monkeypatch.setattr(streaming, "_resolve_persona_tools", lambda *_a: ["execute_python"])
    monkeypatch.setattr(streaming, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(streaming, "_inject_omlx_options", lambda b, _w: dict(b))
    body = _apply_client_tools_only(workspace_id, {"messages": [], "tools": TOOLS})
    assert body["portal_client_tools_only"] is True
    assert _inject_system_prompt_append(workspace_id, body) == body

    out, effective, has_tools, _ = await streaming._build_streaming_request(
        body, MagicMock(type="omlx"), "m", workspace_id, ""
    )
    assert has_tools and effective == []
    assert out["tools"] == TOOLS and out["tool_choice"] == "auto"


def test_client_tools_alone_do_not_mark_an_unmarked_workspace(monkeypatch):
    workspace_id = "test-tools-merge"
    monkeypatch.setitem(
        streaming.WORKSPACES,
        workspace_id,
        {"system_prompt_append": "\nserver tools prompt"},
    )
    body = {"messages": [], "tools": TOOLS}
    assert _apply_client_tools_only(workspace_id, body) == body
    assert _inject_system_prompt_append(workspace_id, body)["messages"][0]["content"].endswith(
        "server tools prompt"
    )


@pytest.mark.anyio
async def test_client_tools_only_offers_exactly_the_client_tools(monkeypatch):
    backend = MagicMock(type="omlx")
    monkeypatch.setattr(streaming, "_resolve_persona_tools", lambda *a: ["execute_python"])
    monkeypatch.setattr(streaming, "_model_supports_tools", lambda m: True)
    monkeypatch.setattr(streaming, "_inject_omlx_options", lambda b, w: dict(b))
    body = {"messages": [], "tools": TOOLS, "portal_client_tools_only": True}
    out, effective, has_tools, _ = await streaming._build_streaming_request(
        body, backend, "m", "auto-coding", ""
    )
    assert has_tools and effective == []
    assert out["tools"] == TOOLS and out["tool_choice"] == "auto"
    assert "portal_client_tools_only" not in out


# Verbatim from live granite-4.1-8b / oMLX, 2026-10-15 (P-1 follow-up): a stray ")" after a
# complete string value. It reached the client as raw markup.
CAPTURED_STRAY_PAREN = (
    '<tool_call>\n{"name": "execute_python", "arguments": {"code": "print(sum(range(444)))")}}\n'
    "</tool_call>"
)
EXEC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
        },
    }
]


def test_stray_paren_after_a_complete_value_is_repaired() -> None:
    before, calls = salvage_text_tool_calls(CAPTURED_STRAY_PAREN, EXEC_TOOLS)
    assert before == "" and len(calls) == 1
    assert calls[0]["function"]["name"] == "execute_python"
    assert json.loads(calls[0]["function"]["arguments"]) == {"code": "print(sum(range(444)))"}


def test_other_malformation_is_not_guessed() -> None:
    bad = '<tool_call>\n{"name": "execute_python", "arguments": {"code": "x" ]}}\n</tool_call>'
    assert salvage_text_tool_calls(bad, EXEC_TOOLS) == (bad, [])


def test_unparsed_markup_is_never_delivered_as_an_answer() -> None:
    from portal.platform.inference.router.text_tool_calls import drop_unparsed_markup

    text = 'Sure.\n<tool_call>\n{"name": "nope"\n</tool_call>'
    assert drop_unparsed_markup(text) == "Sure."
    assert drop_unparsed_markup("plain answer") == "plain answer"
    assert drop_unparsed_markup("Use <function=x> here") == "Use <function=x> here"


@pytest.mark.anyio
async def test_stream_never_delivers_an_unsalvageable_tool_call_wrapper(monkeypatch):
    hop1 = [
        _frame({"content": '<tool_call>\n{"name": "get_weather", "arguments": {"city" ]}}\n'}),
        _frame({"content": "</tool_call>"}),
        _frame({}, "stop"),
        "data: [DONE]",
    ]
    out, dispatched = await _run(monkeypatch, [hop1])
    assert dispatched == []
    assert "<tool_call>" not in out and "get_weather" not in out
    assert out.count("[DONE]") == 1


# ── Gemma 4 native form (P5-GEMMA4-TOOLTEXT-001) ────────────────────────────
# The format text below is rendered verbatim from the canonical chat template
# shipped inside the served checkpoint (hf-cache
# models--mlx-community--gemma-4-26B-A4B-it-qat-4bit, the auto-documents seat's
# weights) for assistant tool_calls get_weather(city=…, days=…): the template is
# the artifact both engines parse against (Ollama's PARSER gemma4 tokens are the
# same `<|tool_call>call:`/`<|"|>`/`<tool_call|>` set). No stored capture of the
# 2026-11-19 leak exists (traces hold metrics only; the container's logs
# rotated), so this render stands in for the raw text the engines bypass.
GEMMA_CALL = '<|tool_call>call:get_weather{city:<|"|>Paris<|"|>,days:3}<tool_call|>'


def test_salvages_gemma4_native_call() -> None:
    before, calls = salvage_text_tool_calls("Checking Paris.\n" + GEMMA_CALL, TOOLS)
    assert before == "Checking Paris."
    assert calls[0]["function"]["name"] == "get_weather"
    assert json.loads(calls[0]["function"]["arguments"]) == {"city": "Paris", "days": 3}


def test_salvages_multiple_gemma4_calls() -> None:
    content = (
        '<|tool_call>call:get_weather{city:<|"|>Oslo<|"|>}<tool_call|>'
        '<|tool_call>call:get_weather{city:<|"|>Rome<|"|>,days:1}<tool_call|>'
    )
    before, calls = salvage_text_tool_calls(content, TOOLS)
    assert before == ""
    assert [json.loads(c["function"]["arguments"]) for c in calls] == [
        {"city": "Oslo"},
        {"city": "Rome", "days": 1},
    ]
    assert calls[0]["id"] != calls[1]["id"]


def test_salvages_gemma4_nested_and_typed_arguments() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_doc",
                "parameters": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "options": {"type": "object"}},
                },
            },
        }
    ]
    content = (
        '<|tool_call>call:create_doc{title:<|"|>Q3 notes<|"|>,'
        'options:{format:<|"|>md<|"|>,toc:true}}<tool_call|>'
    )
    _, calls = salvage_text_tool_calls(content, tools)
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "title": "Q3 notes",
        "options": {"format": "md", "toc": True},
    }


def test_unterminated_gemma4_call_is_not_salvaged_but_is_withheld() -> None:
    from portal.platform.inference.router.text_tool_calls import drop_unparsed_markup

    content = 'Sure.<|tool_call>call:get_weather{city:<|"|>Paris<|"|>'
    assert salvage_text_tool_calls(content, TOOLS) == (content, [])
    assert drop_unparsed_markup(content) == "Sure."


def test_holdback_holds_gemma4_marker_across_chunks() -> None:
    hb = TextToolCallHoldback()
    assert hb.feed("Weather: <|tool_") == "Weather: "
    assert hb.feed('call>call:get_weather{city:<|"|>Paris<|"|>}<tool_call|>') == ""
    assert hb.holding
    assert hb.take().startswith("<|tool_call>")


@pytest.mark.anyio
async def test_stream_dispatches_gemma4_native_call_written_as_text(monkeypatch):
    hop1 = [
        _frame({"content": "Checking. <|tool_"}),
        _frame({"content": 'call>call:get_weather{city:<|"|>Paris<|"|>,days:3}<tool_call|>'}),
        _frame({}, "stop"),
        "data: [DONE]",
    ]
    hop2 = [_frame({"content": "It is 18 C and sunny."}), _frame({}, "stop"), "data: [DONE]"]
    out, dispatched = await _run(monkeypatch, [hop1, hop2])
    assert len(dispatched) == 1
    assert json.loads(dispatched[0][0]["function"]["arguments"]) == {"city": "Paris", "days": 3}
    assert "<|tool_call>" not in out and "get_weather" not in out
    assert "Checking." in out and "sunny" in out
    assert out.count("[DONE]") == 1


def test_non_stream_recovers_gemma4_call_and_sets_finish_reason() -> None:
    from portal.platform.inference.router import non_streaming

    data = {
        "choices": [
            {"message": {"role": "assistant", "content": "Checking.\n" + GEMMA_CALL}},
        ]
    }
    non_streaming._recover_or_withhold_markup(data, TOOLS, "gemma4", "auto-documents")
    msg = data["choices"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "get_weather"
    assert json.loads(msg["tool_calls"][0]["function"]["arguments"]) == {
        "city": "Paris",
        "days": 3,
    }
    assert data["choices"][0]["finish_reason"] == "tool_calls"
    assert "<|tool_call>" not in msg["content"]


def test_non_stream_withholds_unparseable_gemma4_call() -> None:
    from portal.platform.inference.router import non_streaming

    data = {
        "choices": [
            {"message": {"role": "assistant", "content": "Answer.\n<|tool_call>call:get_weather{"}},
        ]
    }
    non_streaming._recover_or_withhold_markup(data, TOOLS, "gemma4", "auto-documents")
    assert data["choices"][0]["message"]["content"] == "Answer."
    assert "tool_calls" not in data["choices"][0]["message"]
