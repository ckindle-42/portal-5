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
    assert streamed.reasoning_tokens == 5
    assert streamed.answer_tokens == 6
    assert streamed.reasoning_deltas == streamed.answer_deltas == 1
    assert streamed.split_source == "deltas"
    assert nonstream.answer_tokens == 6  # apportioned by the two message text lengths
    assert nonstream.split_source == "chars"


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
    assert streamed.reasoning_tokens == 3
    assert streamed.answer_tokens == 3
    assert streamed.reasoning_deltas == streamed.answer_deltas == 1
    assert streamed.reasoning_chars == len("Reason")
    assert streamed.answer_chars == len("Answer")
    assert streamed.split_source == "deltas"
    assert streamed.answer_tps > 0
    assert nonstream.total_s == 1.4
    assert nonstream.answer_tokens == 6


def test_report_speed_summary_uses_median_and_nearest_rank_p90():
    speed = report._speed_summary(
        [
            {
                "answer_tokens": 31,
                "answer_tps": 10,
                "ttft_s": 0.2,
                "total_s": 1.0,
                "completion_tokens": 100,
                "reasoning_s": 1,
                "answer_s": 1,
            },
            {
                "answer_tokens": 32,
                "answer_tps": 20,
                "ttft_s": 0.4,
                "total_s": 2.0,
                "completion_tokens": 300,
                "reasoning_s": 1,
                "answer_s": 2,
            },
            {
                "answer_tokens": 64,
                "answer_tps": 30,
                "ttft_s": 0.6,
                "total_s": 3.0,
                "completion_tokens": 900,
                "reasoning_s": 2,
                "answer_s": 1,
            },
        ]
    )
    assert speed == {
        "answer_tps_median": 25,
        "answer_tps_p90": 30,
        "answer_tps_n": 2,
        "decode_tps_median": 100,
        "decode_tps_p90": 300,
        "decode_tps_n": 3,
        "ttft_s_median": 0.4,
        "ttft_s_p90": 0.6,
        "ttft_s_n": 3,
        "total_s_median": 2,
        "total_s_p90": 3,
        "total_s_n": 3,
    }


def test_logic_grid_legacy_answer_rate_is_rederived_from_character_split():
    row = {
        "economics": {
            "completion_tokens": 2034,
            "reasoning_tokens": 1713,
            "answer_tokens": 321,
            "answer_tps": 1219.503,
            "reasoning_s": 45.761241,
            "answer_s": 0.263222,
            "ttft_s": 0.324508,
            "total_s": 46.343497,
            "timing_source": "engine",
        },
        "transcript": [{"reasoning_chars": 6013}],
        "final_text": "x" * 32,
    }

    speed = report._speed_economics(row)

    assert speed["answer_tokens"] == 11
    assert 10 <= speed["answer_tokens"] <= 12
    assert speed["answer_tps"] is None
    assert speed["decode_tps"] == 2034 / (45.761241 + 0.263222)
    summary = report._speed_summary([row])
    assert summary["answer_tps_median"] is None
    assert summary["answer_tps_n"] == 0
    assert summary["decode_tps_n"] == 1


def test_report_speed_table_prioritizes_decode_and_ttft_and_shows_median_counts():
    lines = []
    speed = report._speed_summary(
        [
            {
                "answer_tokens": 31,
                "answer_tps": 100,
                "completion_tokens": 100,
                "reasoning_s": 0.5,
                "answer_s": 0.5,
                "ttft_s": 0.2,
                "total_s": 1,
            },
            {
                "answer_tokens": 32,
                "answer_tps": 50,
                "completion_tokens": 100,
                "reasoning_s": 0.5,
                "answer_s": 0.5,
                "ttft_s": 0.4,
                "total_s": 2,
            },
        ]
    )
    report._sec_speed(
        lines.append,
        {
            "matrix": [
                {
                    "workspace": "auto",
                    "is_home": True,
                    "suite": "home",
                    "arm": "test-arm",
                    "speed": speed,
                    "role": "candidate",
                    "persona": None,
                    "passes": 0,
                    "n": 0,
                    "instrument_excluded": 0,
                    "median_tokens": None,
                    "median_wall_s": None,
                }
            ]
        },
    )

    speed_table = "\n".join(lines)
    header = next(line for line in lines if line.startswith("| Workspace"))
    assert header.index("Decode tok/s") < header.index("TTFT s") < header.index("Answer tok/s")
    assert "Decode tok/s med (n)" in header
    assert "TTFT s med (n)" in header
    assert "(n=2)" in speed_table
    assert "(n=1)" in speed_table


def test_row_economics_roll_up_turn_timings_and_preserve_first_ttft():
    row = Economics()
    row.merge(
        Economics(
            ttft_s=0.3,
            answer_tokens=3,
            answer_s=0.5,
            total_s=0.8,
            timing_source="engine",
            reasoning_deltas=2,
            answer_deltas=1,
            reasoning_chars=9,
            answer_chars=4,
            split_source="deltas",
        )
    )
    row.merge(
        Economics(
            ttft_s=0.5,
            answer_tokens=5,
            answer_s=1.0,
            total_s=1.5,
            timing_source="engine",
            reasoning_deltas=4,
            answer_deltas=2,
            reasoning_chars=11,
            answer_chars=5,
            split_source="chars",
        )
    )
    assert row.ttft_s == 0.3
    assert row.answer_tokens == 8
    assert row.answer_s == 1.5
    assert row.total_s == 2.3
    assert row.answer_tps == 5.333
    assert row.timing_source == "engine"
    assert row.reasoning_deltas == 6 and row.answer_deltas == 3
    assert row.reasoning_chars == 20 and row.answer_chars == 9
    assert row.split_source == "chars"
