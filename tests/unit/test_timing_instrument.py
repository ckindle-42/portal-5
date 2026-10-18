"""Timing metadata remains additive to Ollama and OpenAI stream contracts."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from portal.platform.inference.ollama_native import native_stream_to_sse, to_openai_completion
from portal.platform.inference.router import non_streaming
from portal.platform.inference.router.handlers import _with_portal_timings
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
    }

    response = to_openai_completion(native)

    assert response["choices"][0]["message"]["content"] == "Answer"
    assert response["choices"][0]["message"]["reasoning"] == "Reason"
    assert response["portal_timings"]["prefill_s"] == 2.0
    assert response["portal_timings"]["total_s"] == 3.5
    assert response["portal_timings"]["timing_source"] == "engine"


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
        "reasoning_s": 0.2,
        "answer_tokens": 2,
        "answer_s": 0.4,
        "answer_tps": 5.0,
        "tool_s": None,
        "total_s": 0.8,
        "timing_source": "measured",
    }


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
