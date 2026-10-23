"""Unit tests for scripts/speed_bench.py — no network; HTTP layer is mocked.

Covers the tok/s arithmetic each engine path parses (Ollama nanoseconds, oMLX
OpenAI usage, Pipeline portal_timings), the client-side fallback when oMLX
reports no split, the table/JSON output, and non-zero exits naming failed sizes.
"""

import argparse
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "speed_bench",
    Path(__file__).resolve().parents[2] / "scripts" / "speed_bench.py",
)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

# Canned non-streaming /api/chat body: durations in nanoseconds.
CANNED = {
    "prompt_eval_count": 1980,
    "prompt_eval_duration": 2_000_000_000,  # 2.0 s
    "eval_count": 128,
    "eval_duration": 6_400_000_000,  # 6.4 s
    "load_duration": 500_000_000,  # 0.5 s
}

# Canned oMLX /v1/chat/completions body: durations in seconds inside usage.
CANNED_OMLX = {
    "choices": [{"message": {"content": "Answer"}, "finish_reason": "stop"}],
    "usage": {
        "prompt_tokens": 1980,
        "completion_tokens": 128,
        "total_tokens": 2108,
        "time_to_first_token": 2.05,
        "prompt_eval_duration": 2.0,
        "generation_duration": 6.4,
        "generation_tokens_per_second": 20.0,
        "model_load_duration": 0.5,
        "total_time": 8.45,
    },
}

# Canned Pipeline SSE stream: one content frame, the timing frame, usage, [DONE].
CANNED_SSE = [
    'data: {"choices":[{"delta":{"content":"Answer"},"finish_reason":null}]}',
    "",
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"portal_timings":'
    '{"prefill_s":1.5,"ttft_s":1.6,"answer_tps":24.0,"total_s":7.0,"timing_source":"engine"}}',
    "",
    'data: {"choices":[],"usage":{"prompt_tokens":3000,"completion_tokens":128},'
    '"portal_timings":{"prefill_s":1.5,"ttft_s":1.6,"answer_tps":24.0,'
    '"total_s":7.0,"timing_source":"engine"}}',
    "",
    "data: [DONE]",
    "",
]


def test_speed_metrics_tps_from_canned_response():
    m = bench.speed_metrics(CANNED)
    assert m["prompt_tokens"] == 1980
    assert m["prefill_tps"] == pytest.approx(1980 / 2.0)  # 990.0 tok/s
    assert m["decode_tps"] == pytest.approx(128 / 6.4)  # 20.0 tok/s
    assert m["load_seconds"] == pytest.approx(0.5)
    assert m["timing_source"] == "engine"


def test_speed_metrics_zero_or_missing_fields():
    m = bench.speed_metrics({"eval_count": 8, "eval_duration": 0})
    assert m["prefill_tps"] == 0.0
    assert m["decode_tps"] == 0.0
    assert m["load_seconds"] == 0.0


def test_omlx_metrics_reads_engine_usage_timings():
    m = bench.omlx_metrics(CANNED_OMLX)
    assert m["prompt_tokens"] == 1980
    assert m["prefill_tps"] == pytest.approx(990.0)
    assert m["decode_tps"] == pytest.approx(20.0)
    assert m["ttft_s"] == pytest.approx(2.05)
    assert m["total_s"] == pytest.approx(8.45)
    assert m["load_seconds"] == pytest.approx(0.5)
    assert m["timing_source"] == "engine"


def test_omlx_metrics_derives_decode_rate_when_absent():
    body = {"usage": {"prompt_tokens": 100, "completion_tokens": 50, "generation_duration": 2.0}}
    m = bench.omlx_metrics(body)
    assert m["decode_tps"] == pytest.approx(25.0)
    assert m["prefill_tps"] is None


def test_omlx_metrics_without_usage_reports_nothing():
    m = bench.omlx_metrics({"choices": []})
    assert m["prefill_tps"] is None and m["decode_tps"] is None
    assert m["timing_source"] == "engine"


def test_pipeline_metrics_maps_portal_timings_and_usage():
    timings = {"prefill_s": 1.5, "ttft_s": 1.6, "answer_tps": 24.0, "total_s": 7.0}
    m = bench.pipeline_metrics(timings, {"prompt_tokens": 3000})
    assert m["prompt_tokens"] == 3000
    assert m["prefill_tps"] == pytest.approx(2000.0)
    assert m["decode_tps"] == pytest.approx(24.0)
    assert m["ttft_s"] == pytest.approx(1.6)
    assert m["load_seconds"] is None
    assert m["timing_source"] == "measured"


def test_pipeline_metrics_without_prompt_count_keeps_prefill_unknown():
    m = bench.pipeline_metrics({"prefill_s": 1.5, "answer_tps": 24.0}, {})
    assert m["prompt_tokens"] is None and m["prefill_tps"] is None


def test_parse_sse_timings_returns_last_frame_and_usage():
    timings, usage = bench.parse_sse_timings(CANNED_SSE)
    assert timings["answer_tps"] == pytest.approx(24.0)
    assert usage["prompt_tokens"] == 3000


def test_parse_sse_timings_skips_blank_and_unparseable_lines():
    lines = ["", ": keepalive", "data: not-json", "data: [DONE]", ""]
    assert bench.parse_sse_timings(lines) == ({}, {})


def test_stream_wall_times_ttft_and_total():
    ticks = iter((10.0, 10.1, 10.5, 12.0))
    lines = [
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',
        'data: {"choices":[{"delta":{"content":"Hi"}}]}',
        'data: {"choices":[],"usage":{"completion_tokens":4}}',
        "data: [DONE]",
    ]
    wall = bench.stream_wall(lines, clock=lambda: next(ticks))
    assert wall["ttft_s"] == pytest.approx(0.5)
    assert wall["total_s"] == pytest.approx(2.0)
    assert wall["usage"]["completion_tokens"] == 4


def test_filler_prompt_length_and_determinism():
    for tokens in (2000, 8000, 32000):
        prompt = bench.build_filler_prompt(tokens)
        assert len(prompt) == tokens * 4
        assert bench.build_filler_prompt(tokens) == prompt


def test_format_table_one_row_per_size():
    rows = [
        {
            "size_tokens": 2000,
            "prompt_tokens": 1980,
            "prefill_tps": 990.1,
            "decode_tps": 20.04,
            "load_seconds": 0.5,
        },
        {
            "size_tokens": 32000,
            "prompt_tokens": 31900,
            "prefill_tps": 400.2,
            "decode_tps": 19.7,
            "load_seconds": 0.0,
        },
    ]
    lines = bench.format_table(rows).splitlines()
    assert len(lines) == 3
    assert lines[0].split() == [
        "size",
        "prompt",
        "prefill",
        "tok/s",
        "decode",
        "tok/s",
        "load",
        "s",
    ]
    assert "1980" in lines[1] and "990.1" in lines[1] and "0.500" in lines[1]
    assert "31900" in lines[2] and "400.2" in lines[2]


def test_format_table_dashes_metrics_the_engine_did_not_report():
    rows = [
        {
            "size_tokens": 2000,
            "prompt_tokens": None,
            "prefill_tps": None,
            "decode_tps": 24.0,
            "load_seconds": None,
        }
    ]
    lines = bench.format_table(rows).splitlines()
    assert lines[1].split() == ["2000", "-", "-", "24.0", "-"]


def test_run_bench_ollama_prints_table_and_writes_out(monkeypatch, capsys, tmp_path):
    def fake_chat(host, model, prompt, timeout=600.0):
        assert host == "http://h:1"
        assert len(prompt) == 2000 * 4  # sizes are per-request; 2000 here
        return CANNED

    monkeypatch.setattr(bench, "request_chat", fake_chat)
    out_file = tmp_path / "report.json"
    code = bench.run_bench("ollama", "http://h:1", "model-a", [2000], out=str(out_file))

    assert code == 0
    printed = capsys.readouterr().out
    assert "990.0" in printed and "20.0" in printed and "0.500" in printed
    report = json.loads(out_file.read_text())
    assert report["engine"] == "ollama"
    assert report["model"] == "model-a"
    assert report["failures"] == []
    assert [r["size_tokens"] for r in report["results"]] == [2000]


def test_run_bench_omlx_uses_engine_timings(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_omlx(host, model, prompt, api_key="", timeout=600.0):
        calls.append((host, model, api_key))
        return CANNED_OMLX

    monkeypatch.setattr(bench, "request_omlx", fake_omlx)
    monkeypatch.setattr(
        bench, "request_omlx_streamed", lambda *a, **k: pytest.fail("fallback must not run")
    )
    out_file = tmp_path / "report.json"
    code = bench.run_bench("omlx", "http://h:2", "model-b", [2000], out=str(out_file), api_key="k")

    assert code == 0
    assert calls == [("http://h:2", "model-b", "k")]
    captured = capsys.readouterr()
    assert "990.0" in captured.out and "20.0" in captured.out
    assert "measured" not in captured.err
    row = json.loads(out_file.read_text())["results"][0]
    assert row["ttft_s"] == pytest.approx(2.05)
    assert row["timing_source"] == "engine"


def test_run_bench_omlx_falls_back_to_client_side_timing(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(bench, "request_omlx", lambda *a, **k: {"choices": []})
    monkeypatch.setattr(
        bench,
        "request_omlx_streamed",
        lambda *a, **k: {
            "ttft_s": 1.0,
            "total_s": 5.0,
            "usage": {"prompt_tokens": 2000, "completion_tokens": 128},
        },
    )
    out_file = tmp_path / "report.json"
    code = bench.run_bench("omlx", "http://h:2", "model-b", [2000], out=str(out_file))

    assert code == 0
    captured = capsys.readouterr()
    assert "no prefill/decode split" in captured.err and "size 2000" in captured.err
    row = json.loads(out_file.read_text())["results"][0]
    assert row["timing_source"] == "measured"
    assert row["ttft_s"] == pytest.approx(1.0)
    assert row["prefill_tps"] == pytest.approx(2000.0)
    assert row["decode_tps"] == pytest.approx(32.0)


def test_run_bench_pipeline_reads_portal_timings(monkeypatch, capsys, tmp_path):
    seen = {}

    def fake_pipeline(host, workspace, prompt, api_key="", timeout=600.0):
        seen.update(host=host, workspace=workspace, api_key=api_key)
        return bench.parse_sse_timings(CANNED_SSE)

    monkeypatch.setattr(bench, "request_pipeline", fake_pipeline)
    out_file = tmp_path / "report.json"
    code = bench.run_bench(
        "pipeline", "http://p:9", "auto-coding", [2000], out=str(out_file), api_key="pk"
    )

    assert code == 0
    assert seen == {"host": "http://p:9", "workspace": "auto-coding", "api_key": "pk"}
    printed = capsys.readouterr().out
    assert "2000.0" in printed and "24.0" in printed  # 3000 tokens / 1.5 s prefill
    row = json.loads(out_file.read_text())["results"][0]
    assert row["prompt_tokens"] == 3000
    assert row["ttft_s"] == pytest.approx(1.6)
    assert row["total_s"] == pytest.approx(7.0)
    assert row["load_seconds"] is None


def test_run_bench_pipeline_without_timings_fails_by_size(monkeypatch, capsys):
    monkeypatch.setattr(bench, "request_pipeline", lambda *a, **k: ({}, {}))
    code = bench.run_bench("pipeline", "http://p:9", "auto-coding", [100, 200])

    err = capsys.readouterr().err
    assert code != 0
    assert "size 100" in err and "size 200" in err
    assert "no portal_timings" in err


def test_run_bench_failed_request_gives_nonzero_exit(monkeypatch, capsys):
    def fake_chat(host, model, prompt, timeout=600.0):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(bench, "request_chat", fake_chat)
    code = bench.run_bench("ollama", "http://h:1", "model-a", [100, 200])

    err = capsys.readouterr().err
    assert code != 0
    assert "size 100" in err and "size 200" in err


def test_parse_sizes():
    assert bench.parse_sizes("2000,8000,32000") == [2000, 8000, 32000]
    for bad in ("abc", "100,-5", ",,"):
        with pytest.raises(argparse.ArgumentTypeError):
            bench.parse_sizes(bad)


def test_resolve_url_precedence(monkeypatch):
    monkeypatch.setenv("OMLX_URL", "http://from-env:1")
    assert bench.resolve_url("omlx", "http://flag:2") == "http://flag:2"
    assert bench.resolve_url("omlx") == "http://from-env:1"
    monkeypatch.delenv("OMLX_URL")
    assert bench.resolve_url("omlx") == bench.DEFAULT_URLS["omlx"]


def test_engine_key_reads_env_then_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('PIPELINE_API_KEY="from-file"\n')
    monkeypatch.setattr(bench, "_ENV_FILE", env_file)
    monkeypatch.delenv("PIPELINE_API_KEY", raising=False)
    assert bench.engine_key("pipeline") == "from-file"
    monkeypatch.setenv("PIPELINE_API_KEY", "from-env")
    assert bench.engine_key("pipeline") == "from-env"
    assert bench.engine_key("ollama") == ""


def test_main_dispatches_pipeline_workspace(monkeypatch):
    seen = {}

    def fake_run(engine, host, target, sizes, *, out=None, api_key="", timeout=600.0):
        seen.update(
            engine=engine, host=host, target=target, sizes=sizes, api_key=api_key, timeout=timeout
        )
        return 0

    monkeypatch.setattr(bench, "run_bench", fake_run)
    monkeypatch.setenv("PIPELINE_URL", "http://pipe:9099")
    monkeypatch.setenv("PIPELINE_API_KEY", "pk")
    code = bench.main(["--engine", "pipeline", "--workspace", "auto-coding", "--sizes", "2000"])

    assert code == 0
    assert seen == {
        "engine": "pipeline",
        "host": "http://pipe:9099",
        "target": "auto-coding",
        "sizes": [2000],
        "api_key": "pk",
        "timeout": 600.0,
    }


def test_main_requires_a_target_for_each_engine(capsys):
    with pytest.raises(SystemExit):
        bench.main(["--engine", "pipeline"])
    with pytest.raises(SystemExit):
        bench.main(["--engine", "ollama"])
