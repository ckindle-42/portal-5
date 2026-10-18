"""Unit tests for scripts/ollama_speed_bench.py — no network; HTTP layer is mocked.

Covers the tok/s arithmetic from a canned response, the filler-prompt length,
the table output, and a failed request returning a non-zero exit code.
"""

import argparse
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "ollama_speed_bench",
    Path(__file__).resolve().parents[2] / "scripts" / "ollama_speed_bench.py",
)
obench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(obench)

# Canned non-streaming /api/chat body: durations in nanoseconds.
CANNED = {
    "prompt_eval_count": 1980,
    "prompt_eval_duration": 2_000_000_000,  # 2.0 s
    "eval_count": 128,
    "eval_duration": 6_400_000_000,  # 6.4 s
    "load_duration": 500_000_000,  # 0.5 s
}


def test_speed_metrics_tps_from_canned_response():
    m = obench.speed_metrics(CANNED)
    assert m["prompt_tokens"] == 1980
    assert m["prefill_tps"] == pytest.approx(1980 / 2.0)  # 990.0 tok/s
    assert m["decode_tps"] == pytest.approx(128 / 6.4)  # 20.0 tok/s
    assert m["load_seconds"] == pytest.approx(0.5)


def test_speed_metrics_zero_or_missing_fields():
    m = obench.speed_metrics({"eval_count": 8, "eval_duration": 0})
    assert m["prefill_tps"] == 0.0
    assert m["decode_tps"] == 0.0
    assert m["load_seconds"] == 0.0


def test_filler_prompt_length_and_determinism():
    for tokens in (2000, 8000, 32000):
        prompt = obench.build_filler_prompt(tokens)
        assert len(prompt) == tokens * 4
        assert obench.build_filler_prompt(tokens) == prompt


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
    lines = obench.format_table(rows).splitlines()
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


def test_run_bench_success_prints_table_and_writes_out(monkeypatch, capsys, tmp_path):
    def fake_chat(host, model, prompt):
        assert host == "http://h:1"
        assert len(prompt) == 2000 * 4  # sizes are per-request; 2000 here
        return CANNED

    monkeypatch.setattr(obench, "request_chat", fake_chat)
    out_file = tmp_path / "report.json"
    code = obench.run_bench("http://h:1", "model-a", [2000], out=str(out_file))

    assert code == 0
    printed = capsys.readouterr().out
    assert "990.0" in printed and "20.0" in printed and "0.500" in printed
    report = json.loads(out_file.read_text())
    assert report["model"] == "model-a"
    assert report["failures"] == []
    assert [r["size_tokens"] for r in report["results"]] == [2000]


def test_run_bench_failed_request_gives_nonzero_exit(monkeypatch, capsys):
    def fake_chat(host, model, prompt):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(obench, "request_chat", fake_chat)
    code = obench.run_bench("http://h:1", "model-a", [100, 200])

    err = capsys.readouterr().err
    assert code != 0
    assert "size 100" in err and "size 200" in err


def test_parse_sizes():
    assert obench.parse_sizes("2000,8000,32000") == [2000, 8000, 32000]
    for bad in ("abc", "100,-5", ",,"):
        with pytest.raises(argparse.ArgumentTypeError):
            obench.parse_sizes(bad)
