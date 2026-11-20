"""speed_bench pipeline rows name the serving model and the engine-side cold load.

The 2026-11-20 oMLX 0.8.0 gate produced rows whose slowness was a hidden model
load (``model_load_duration``), not engine speed — the row carried neither the
served model nor the load time, so cold rows were indistinguishable from
regressions.
"""

from __future__ import annotations

from scripts.speed_bench import parse_sse_timings, pipeline_metrics


def test_pipeline_row_carries_served_model_load_and_completion():
    lines = [
        b'data: {"model": "Huihui-Qwen3.6-27B-abliterated-MLX-4bit", '
        b'"choices": [{"delta": {"content": "hi"}}]}\n\n',
        b'data: {"portal_timings": {"answer_tps": 5.1, "ttft_s": 1.0, '
        b'"total_s": 25.9, "timing_source": "engine"}}\n\n',
        b'data: {"usage": {"prompt_tokens": 7670, "completion_tokens": 128, '
        b'"model_load_duration": 11.42}}\n\n',
        b"data: [DONE]\n\n",
    ]
    timings, usage, served = parse_sse_timings(lines)
    row = pipeline_metrics(timings, usage, served)
    assert row["served_model"] == "Huihui-Qwen3.6-27B-abliterated-MLX-4bit"
    assert row["load_seconds"] == 11.42
    assert row["completion_tokens"] == 128
    assert row["decode_tps"] == 5.1


def test_pipeline_row_without_usage_leaves_the_new_fields_none():
    timings, usage, served = parse_sse_timings(
        [b'data: {"portal_timings": {}}\n\n', b"data: [DONE]\n\n"]
    )
    row = pipeline_metrics(timings, usage, served)
    assert served is None
    assert row["load_seconds"] is None
    assert row["completion_tokens"] is None
