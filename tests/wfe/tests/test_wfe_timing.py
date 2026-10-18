"""Offline Ollama/oMLX timing payload contracts for the WFE runner/report."""

from __future__ import annotations

import io
import json

from tests.wfe import report
from tests.wfe.runner import _parse_stream_v1, _read_response, _read_stream
from tests.wfe.schema import Economics

OLLAMA_NONSTREAM = {
    "model": "recorded-ollama",
    "message": {"role": "assistant", "thinking": "Reason", "content": "Answer"},
    "prompt_eval_count": 24,
    "eval_count": 11,
    "prompt_eval_duration": 1_250_000_000,
    "eval_duration": 2_500_000_000,
}

OMLX_NONSTREAM = {
    "model": "recorded-omlx",
    "choices": [
        {
            "message": {"role": "assistant", "reasoning_content": None, "content": "Answer"},
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 24,
        "completion_tokens": 6,
        "total_tokens": 30,
        "prompt_tokens_details": {"cached_tokens": 8},
        "model_load_duration": 0.0,
        "total_time": 1.4,
    },
}


def test_ollama_native_stream_and_nonstream_payloads_keep_engine_timings():
    stream_records = [
        {"model": "recorded-ollama", "message": {"thinking": "Reason"}},
        {"model": "recorded-ollama", "message": {"content": "Answer"}},
        {
            "model": "recorded-ollama",
            "done": True,
            "done_reason": "stop",
            "message": {"content": "", "thinking": ""},
            "prompt_eval_count": 24,
            "eval_count": 11,
            "prompt_eval_duration": 1_250_000_000,
            "eval_duration": 2_500_000_000,
        },
    ]
    message, _finish, streamed = _read_stream(
        "api", [f"{json.dumps(row)}\n".encode() for row in stream_records]
    )
    _, _, nonstream = _read_response("api", io.StringIO(json.dumps(OLLAMA_NONSTREAM)))

    assert message["content"] == "Answer"
    assert streamed.timing_source == nonstream.timing_source == "engine"
    assert streamed.prefill_s == nonstream.prefill_s == 1.25
    assert streamed.total_s == nonstream.total_s == 3.75
    assert streamed.answer_tokens == 10
    assert nonstream.answer_tokens is None  # the native payload has no per-phase token counts


def test_omlx_stream_and_nonstream_payloads_keep_engine_timings():
    events = [
        {"choices": [{"delta": {"reasoning_content": "Reason"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "Answer"}, "finish_reason": None}]},
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 24,
                "completion_tokens": 6,
                "total_tokens": 30,
                "prompt_tokens_details": {"cached_tokens": 8},
                "time_to_first_token": 0.42,
                "prompt_eval_duration": 0.4,
                "generation_duration": 1.2,
                "total_time": 1.65,
            },
        },
        "[DONE]",
    ]
    lines = [
        ("data: " + (event if isinstance(event, str) else json.dumps(event)) + "\n\n").encode()
        for event in events
    ]
    parsed = _parse_stream_v1(line.decode() for line in lines)
    _, _, nonstream = _read_response("v1", io.StringIO(json.dumps(OMLX_NONSTREAM)))
    streamed = Economics(**parsed["portal_timings"])

    assert streamed.timing_source == nonstream.timing_source == "engine"
    assert streamed.prefill_s == 0.4
    assert streamed.ttft_s == 0.42
    assert streamed.total_s == 1.65
    assert streamed.reasoning_tokens == 1
    assert streamed.answer_tokens == 5
    assert streamed.answer_tps > 0
    assert nonstream.total_s == 1.4
    assert nonstream.answer_tokens == 6


def test_report_speed_summary_uses_median_and_nearest_rank_p90():
    speed = report._speed_summary(
        [
            {"answer_tps": 10, "ttft_s": 0.2, "total_s": 1.0},
            {"answer_tps": 20, "ttft_s": 0.4, "total_s": 2.0},
            {"answer_tps": 30, "ttft_s": 0.6, "total_s": 3.0},
        ]
    )
    assert speed == {
        "answer_tps_median": 20,
        "answer_tps_p90": 30,
        "ttft_s_median": 0.4,
        "ttft_s_p90": 0.6,
        "total_s_median": 2,
        "total_s_p90": 3,
    }


def test_row_economics_roll_up_turn_timings_and_preserve_first_ttft():
    row = Economics()
    row.merge(
        Economics(ttft_s=0.3, answer_tokens=3, answer_s=0.5, total_s=0.8, timing_source="engine")
    )
    row.merge(
        Economics(ttft_s=0.5, answer_tokens=5, answer_s=1.0, total_s=1.5, timing_source="engine")
    )
    assert row.ttft_s == 0.3
    assert row.answer_tokens == 8
    assert row.answer_s == 1.5
    assert row.total_s == 2.3
    assert row.answer_tps == 5.333
    assert row.timing_source == "engine"
