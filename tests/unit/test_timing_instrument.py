"""Timing metadata remains additive to Ollama and OpenAI stream contracts."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from portal.platform.inference.ollama_native import native_stream_to_sse, to_openai_completion
from portal.platform.inference.router import non_streaming, streaming
from portal.platform.inference.router.handlers import _with_portal_timings
from portal.platform.inference.router.metrics import (
    _answer_seconds,
    _answer_tokens,
    _decode_seconds,
    _decode_tokens,
    _ttft_seconds,
)
from portal.platform.inference.router.trace import (
    StreamMeasurement,
    TurnTrace,
    add_model_turn,
    add_tool_time,
    current_portal_timings,
    normalize_engine_timings,
    start_timings,
)


def test_ollama_native_completion_surfaces_engine_timings_without_changing_message():
    native = {
        "model": "recorded-ollama",
        "message": {"role": "assistant", "content": "Answer", "thinking": "Reason"},
        "done_reason": "stop",
        "prompt_eval_count": 12,
        "eval_count": 7,
        "prompt_eval_duration": 2_000_000_000,
        "eval_duration": 1_500_000_000,
        "load_duration": 4_000_000_000,
    }

    response = to_openai_completion(native)

    assert response["choices"][0]["message"]["content"] == "Answer"
    assert response["choices"][0]["message"]["reasoning"] == "Reason"
    assert response["portal_timings"]["prefill_s"] == 2.0
    assert response["portal_timings"]["total_s"] == 3.5
    assert response["portal_timings"]["timing_source"] == "engine"
    # Cold load is not a portal_timings field. Keep the native nanoseconds on
    # the translated body so a council stage can record them.
    assert response["load_duration"] == 4_000_000_000


@pytest.mark.anyio
async def test_ollama_native_stream_has_engine_timings_on_terminal_frames():
    rows = [
        {
            "model": "recorded-ollama",
            "message": {"thinking": "Reason"},
            "done": False,
        },
        {
            "model": "recorded-ollama",
            "message": {"content": "Answer"},
            "done": False,
        },
        {
            "model": "recorded-ollama",
            "message": {"content": "", "thinking": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 12,
            "eval_count": 7,
            "prompt_eval_duration": 2_000_000_000,
            "eval_duration": 1_500_000_000,
        },
    ]

    async def lines():
        for row in rows:
            yield json.dumps(row)

    frames = [
        json.loads(frame[6:])
        async for frame in native_stream_to_sse(lines(), include_usage=True)
        if frame.startswith(b"data: {")
    ]
    assert frames[-2]["portal_timings"]["prefill_s"] == 2.0
    assert frames[-1]["portal_timings"]["total_s"] == 3.5
    assert frames[-1]["usage"]["completion_tokens"] == 7


def test_engine_shapes_and_measured_fallback_normalize_to_same_fields():
    ollama = normalize_engine_timings(
        {
            "message": {"content": "Answer", "thinking": "Reason"},
            "prompt_eval_count": 20,
            "eval_count": 9,
            "prompt_eval_duration": 1_000_000_000,
            "eval_duration": 2_000_000_000,
        },
        {
            "ttft_s": 1.1,
            "reasoning_tokens": 4,
            "reasoning_deltas": 4,
            "answer_deltas": 5,
            "reasoning_s": 1.0,
            "answer_tokens": 5,
            "answer_s": 1.0,
            "total_s": 3.0,
        },
    )
    omlx = normalize_engine_timings(
        {
            "choices": [{"message": {"content": "Answer"}}],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 5,
                "total_tokens": 25,
                "time_to_first_token": 0.4,
                "prompt_eval_duration": 0.35,
                "generation_duration": 0.8,
                "total_time": 1.2,
            },
        }
    )

    assert ollama["timing_source"] == "engine"
    assert (ollama["prefill_s"], ollama["ttft_s"], ollama["answer_tokens"]) == (
        1.0,
        1.1,
        5,
    )
    assert ollama["split_source"] == "deltas"
    assert omlx["timing_source"] == "engine"
    assert (omlx["prefill_s"], omlx["ttft_s"], omlx["total_s"]) == (0.35, 0.4, 1.2)
    assert omlx["answer_tps"] == 6.25


def test_stream_measurement_fills_missing_engine_timings(monkeypatch):
    ticks = iter((10.0, 10.2, 10.4, 10.8))
    monkeypatch.setattr(
        "portal.platform.inference.router.trace.time.monotonic", lambda: next(ticks)
    )
    measurement = StreamMeasurement()
    measurement.observe(
        {"choices": [{"delta": {"content": "<think>Reason"}}]},
        visible_content="",
        content_override=True,
        inline_reasoning=True,
    )
    measurement.observe({"choices": [{"delta": {"content": "A"}}]})
    measurement.observe({"choices": [{"delta": {"content": "nswer"}}]})

    timings = normalize_engine_timings({}, measurement.result())

    assert timings == {
        "prefill_s": 0.2,
        "ttft_s": 0.2,
        "reasoning_tokens": 1,
        "reasoning_deltas": 1,
        "answer_deltas": 2,
        "reasoning_chars": 6,
        "answer_chars": 6,
        "reasoning_s": 0.2,
        "answer_tokens": 2,
        "answer_s": 0.4,
        "answer_tps": 5.0,
        "tool_s": None,
        "total_s": 0.8,
        "timing_source": "measured",
        "split_source": "deltas",
    }


def test_engine_total_with_legacy_delta_split_is_repaired_by_character_evidence():
    data = {
        "message": {"thinking": "r" * 6013, "content": "a" * 32},
        "eval_count": 2034,
        "eval_duration": 46_024_463_000,
        "portal_timings": {
            "reasoning_tokens": 1713,
            "answer_tokens": 321,
            "answer_tps": 1219.503,
            "reasoning_s": 45.761241,
            "answer_s": 0.263222,
            "total_s": 46.343497,
            "timing_source": "engine",
        },
    }

    timings = normalize_engine_timings(data)

    assert timings["reasoning_tokens"] == 2023
    assert timings["answer_tokens"] == 11
    assert timings["answer_tps"] == round(11 / 0.263222, 3)
    assert timings["reasoning_deltas"] is None
    assert timings["answer_deltas"] is None
    assert timings["reasoning_chars"] == 6013
    assert timings["answer_chars"] == 32
    assert timings["split_source"] == "chars"


def test_pipeline_nonstream_body_carries_measured_timings_without_changing_content(monkeypatch):
    start_timings()
    monkeypatch.setattr(non_streaming, "_record_usage", lambda **_kwargs: None)
    data = {
        "choices": [{"message": {"role": "assistant", "content": "Answer"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }

    response = non_streaming._apply_non_stream_response(
        data,
        SimpleNamespace(id="recorded"),
        "wfe",
        "recorded-model",
        time.monotonic() - 0.25,
        model_elapsed_s=0.25,
    )
    body = json.loads(response.body)

    assert body["choices"][0]["message"]["content"] == "Answer"
    assert body["portal_timings"]["total_s"] == 0.25
    assert body["portal_timings"]["answer_tokens"] == 2
    assert body["portal_timings"]["answer_s"] is None
    assert body["portal_timings"]["timing_source"] == "measured"


def test_pipeline_nonstream_passes_engine_timings_to_usage_metrics(monkeypatch):
    start_timings()
    recorded = {}
    monkeypatch.setattr(non_streaming, "_record_usage", lambda **kwargs: recorded.update(kwargs))
    data = {
        "choices": [{"message": {"role": "assistant", "content": "Answer"}}],
        "usage": {
            "prompt_tokens": 24,
            "completion_tokens": 6,
            "time_to_first_token": 0.42,
            "prompt_eval_duration": 0.4,
            "generation_duration": 1.2,
            "total_time": 1.65,
        },
    }

    response = non_streaming._apply_non_stream_response(
        data,
        SimpleNamespace(id="recorded"),
        "wfe",
        "recorded-model",
        time.monotonic() - 1.65,
        model_elapsed_s=1.65,
    )
    body = json.loads(response.body)

    assert body["choices"][0]["message"]["content"] == "Answer"
    assert recorded["decode_seconds"] == 1.2
    assert recorded["ttft_seconds"] == 0.42
    assert recorded["reasoning_tokens"] == 0
    assert recorded["answer_seconds"] == 1.2
    assert recorded["answer_tokens"] == 6


@pytest.mark.anyio
async def test_final_timing_frame_is_inserted_before_done_and_keeps_content():
    start_timings()
    aggregate = add_model_turn(
        {"usage": {"prompt_tokens": 8, "completion_tokens": 2}},
        {
            "prefill_s": 0.2,
            "ttft_s": 0.2,
            "answer_tokens": 2,
            "answer_s": 0.4,
            "total_s": 0.6,
            "reasoning_tokens": 0,
            "reasoning_s": 0,
        },
    )
    add_tool_time(0.75)
    aggregate = current_portal_timings()

    async def source():
        yield b'data: {"choices":[{"delta":{"content":"same"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    frames = [frame async for frame in _with_portal_timings(source())]
    assert b'"content":"same"' in frames[0]
    assert b'"portal_timings"' in frames[1]
    assert json.loads(frames[1][6:])["portal_timings"]["tool_s"] == 0.75
    assert frames[2] == b"data: [DONE]\n\n"
    assert aggregate["tool_s"] == 0.75


def test_trace_record_exposes_timing_metadata():
    trace = TurnTrace("wfe-timing-test")
    trace.set(portal_timings={"prefill_s": 1.0, "timing_source": "engine"})
    assert trace.to_dict()["portal_timings"] == {
        "prefill_s": 1.0,
        "timing_source": "engine",
    }


def _metric_value(metric, **labels):
    return float(metric.labels(**labels)._value.get())


def _metric_sum(metric, **labels):
    return float(metric.labels(**labels)._sum.get())


class _StreamResponse:
    status_code = 200

    def __init__(self, lines):
        self.lines = lines

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class _StreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        return None


class _StreamClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def stream(self, *_args, **_kwargs):
        return _StreamContext(self.responses.pop(0))


def _sse(payload):
    return "data: " + json.dumps(payload, separators=(",", ":"))


def _tool_call_frame():
    return _sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-timing-1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        }
    )


def _tool_turn_usage():
    return _sse(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 22,
                "completion_tokens": 20,
                "completion_tokens_details": {"reasoning_tokens": 12},
                "time_to_first_token": 0.15,
                "prompt_eval_duration": 0.25,
                "generation_duration": 0.5,
                "total_time": 0.8,
            },
        }
    )


def _answer_turn_usage():
    return _sse(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 25,
                "completion_tokens": 40,
                "time_to_first_token": 0.2,
                "prompt_eval_duration": 0.3,
                "generation_duration": 0.6,
                "total_time": 0.95,
            },
        }
    )


@pytest.mark.anyio
async def test_stream_tool_loop_accumulates_each_round_and_records_timing_metrics(monkeypatch):
    model, workspace = "timing-stream-tool-model", "timing-stream-tool-ws"
    start_timings()
    monkeypatch.setattr(
        streaming,
        "_http_client",
        _StreamClient(
            [
                _StreamResponse(
                    [
                        _sse(
                            {
                                "choices": [
                                    {
                                        "delta": {"reasoning": "thinking"},
                                        "finish_reason": None,
                                    }
                                ]
                            }
                        ),
                        _tool_call_frame(),
                        _sse({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
                        _tool_turn_usage(),
                        "data: [DONE]",
                    ]
                ),
                _StreamResponse(
                    [
                        _sse(
                            {
                                "choices": [
                                    {
                                        "delta": {"content": "visible answer " * 40},
                                        "finish_reason": None,
                                    }
                                ]
                            }
                        ),
                        _sse({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
                        _answer_turn_usage(),
                        "data: [DONE]",
                    ]
                ),
            ]
        ),
    )

    async def dispatch(*args, **kwargs):
        add_tool_time(2.5)
        calls = args[0]
        return (
            {"role": "assistant", "content": None, "tool_calls": calls},
            [{"role": "tool", "tool_call_id": "call-timing-1", "name": "lookup", "content": "ok"}],
        )

    monkeypatch.setattr(streaming, "_dispatch_hop_tool_calls", dispatch)
    response = streaming._tool_loop_frames(
        "http://recorded-engine/v1/chat/completions",
        {
            "model": model,
            "stream": True,
            "messages": [{"role": "user", "content": "lookup this"}],
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
        },
        workspace,
        model,
        "",
        {"lookup"},
    )
    chunks = [chunk async for chunk in _with_portal_timings(response)]
    timing_frame = next(
        json.loads(line[6:])
        for chunk in chunks
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
        and line[6:] != "[DONE]"
        and "portal_timings" in json.loads(line[6:])
    )
    timings = timing_frame["portal_timings"]
    labels = {"model": model, "workspace": workspace, "source": "engine"}

    assert timings["prefill_s"] == pytest.approx(0.55)
    assert timings["ttft_s"] == pytest.approx(0.15)
    assert timings["reasoning_tokens"] == 12
    assert timings["answer_tokens"] == 40
    assert timings["answer_s"] == pytest.approx(0.6)
    assert timings["total_s"] == pytest.approx(1.75)
    assert timings["tool_s"] == pytest.approx(2.5)
    assert timings["timing_source"] == "engine"
    assert _metric_value(_decode_tokens, **labels) == 60
    assert _metric_value(_decode_seconds, **labels) == pytest.approx(1.1)
    assert _metric_value(_answer_tokens, **labels) == 40
    assert _metric_value(_answer_seconds, **labels) == pytest.approx(0.6)
    assert _metric_sum(_ttft_seconds, **labels) == pytest.approx(0.35)


class _JsonResponse:
    status_code = 200
    content = b""

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class _NonstreamClient:
    def __init__(self, responses):
        self.responses = list(responses)

    async def post(self, *_args, **_kwargs):
        return _JsonResponse(self.responses.pop(0))


@pytest.mark.anyio
async def test_nonstream_tool_loop_accumulates_each_round_and_records_timing_metrics(
    monkeypatch,
):
    model, workspace = "timing-nonstream-tool-model", "timing-nonstream-tool-ws"
    start_timings()
    tool_call = {
        "id": "call-timing-ns-1",
        "type": "function",
        "function": {"name": "lookup", "arguments": "{}"},
    }
    first_round = {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [tool_call]}}],
        "prompt_eval_count": 18,
        "eval_count": 20,
        "prompt_eval_duration": 250_000_000,
        "eval_duration": 500_000_000,
        "time_to_first_token": 0.1,
    }
    final_round = {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": "visible answer " * 40}}],
        "prompt_eval_count": 25,
        "eval_count": 40,
        "prompt_eval_duration": 300_000_000,
        "eval_duration": 600_000_000,
        "time_to_first_token": 0.2,
    }
    monkeypatch.setattr(non_streaming, "_http_client", _NonstreamClient([first_round, final_round]))
    monkeypatch.setattr(non_streaming, "_resolve_persona_tools", lambda *_args: ["lookup"])
    monkeypatch.setattr(non_streaming, "_model_supports_tools", lambda _model: True)
    monkeypatch.setattr(non_streaming, "_inject_ollama_options", lambda body, _workspace: body)
    monkeypatch.setattr(non_streaming, "_select_explicit_required_tool", lambda *_args: None)
    monkeypatch.setattr(
        non_streaming,
        "_dispatch_tool_call",
        lambda *_args, **_kwargs: _dispatch_tool_result(tool_call),
    )
    from portal.platform.inference.tool_registry import tool_registry

    async def refresh():
        return None

    monkeypatch.setattr(tool_registry, "refresh", refresh)
    monkeypatch.setattr(
        tool_registry,
        "get_openai_tools",
        lambda _names: [{"type": "function", "function": {"name": "lookup"}}],
    )

    async def make_room(*_args):
        return None

    monkeypatch.setattr(
        "portal.platform.inference.router.backend_introspect.make_room_for_omlx", make_room
    )
    monkeypatch.setattr(non_streaming, "registry", None)
    monkeypatch.setattr(
        "portal.platform.inference.router.context_inject.schedule_writeback", lambda *_args: None
    )
    monkeypatch.setitem(non_streaming.WORKSPACES, workspace, {})
    backend = SimpleNamespace(
        id="recorded-ollama",
        type="ollama",
        chat_url="http://recorded-engine/v1/chat/completions",
        models=[model],
        resolve_model=lambda _hint: None,
    )
    response = await non_streaming._try_non_streaming(
        backend,
        {"messages": [{"role": "user", "content": "lookup this"}], "tool_choice": "auto"},
        workspace,
        time.monotonic(),
    )
    body = json.loads(response.body)
    timings = body["portal_timings"]
    labels = {"model": model, "workspace": workspace, "source": "engine"}

    assert timings["prefill_s"] == pytest.approx(0.55)
    assert timings["ttft_s"] == pytest.approx(0.1)
    assert timings["answer_tokens"] == 40
    assert timings["answer_s"] == pytest.approx(0.6)
    assert timings["tool_s"] == pytest.approx(2.5)
    assert timings["timing_source"] == "engine"
    assert _metric_value(_decode_tokens, **labels) == 60
    assert _metric_value(_decode_seconds, **labels) == pytest.approx(1.1)
    assert _metric_value(_answer_tokens, **labels) == 40
    assert _metric_value(_answer_seconds, **labels) == pytest.approx(0.6)
    assert _metric_sum(_ttft_seconds, **labels) == pytest.approx(0.3)


async def _dispatch_tool_result(tool_call):
    add_tool_time(2.5)
    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "name": "lookup",
        "content": "ok",
    }
