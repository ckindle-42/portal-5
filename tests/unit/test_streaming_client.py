"""Stream aggregation preserves answer and reasoning as separate fields."""

from __future__ import annotations

import json

from portal.platform.inference.streaming_client import (
    _take_native_line,
    _take_pipeline_line,
    _Turn,
)


def test_pipeline_sse_keeps_reasoning_out_of_content():
    turn = _Turn()
    _take_pipeline_line(
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "delta": {
                            "reasoning_content": "\nprivate thought",
                            "content": '{"determination":"SUPPORTED"}',
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        ),
        turn,
    )
    assert "".join(turn.reasoning_parts) == "\nprivate thought"
    assert "".join(turn.content_parts) == '{"determination":"SUPPORTED"}'
    assert turn.finish_reason == "stop"


def test_native_stream_keeps_thinking_out_of_content():
    turn = _Turn()
    _take_native_line(
        json.dumps(
            {
                "message": {
                    "role": "assistant",
                    "thinking": "private thought",
                    "content": "final answer",
                },
                "done": True,
                "done_reason": "length",
            }
        ),
        turn,
    )
    assert "".join(turn.reasoning_parts) == "private thought"
    assert "".join(turn.content_parts) == "final answer"
    assert turn.finish_reason == "length"
